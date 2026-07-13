from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.document_vector_repository import DocumentVectorRepository
from app.rag.chunker import Chunker
from app.rag.embeddings import EmbeddingService
from app.rag.indexer import VectorIndex
from app.rag.parsers.base import Parser
from app.rag.parsers.docx_parser import DocxParser
from app.rag.parsers.liteparse_pdf_parser import LiteParsePdfParser
from app.rag.parsers.plain_text_parser import PlainTextParser
from app.services.billing_service import BillingService


class RagIngestionResult:
    def __init__(self, actual_embedding_tokens: int, actual_chunk_count: int, model_version: str) -> None:
        self.actual_embedding_tokens = actual_embedding_tokens
        self.actual_chunk_count = actual_chunk_count
        self.model_version = model_version


class RagIngestionPipeline:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = DocumentVectorRepository(session)
        self.chunker = Chunker(settings.rag_chunk_size, settings.rag_chunk_overlap)
        self.embedding_service = EmbeddingService()
        self.index = VectorIndex()

    async def ingest_file(
        self,
        *,
        file_md5: str,
        file_path: str,
        user_id: str,
        org_tag: str | None,
        is_public: bool,
    ) -> RagIngestionResult:
        parser = self._select_parser(file_path)
        segments = await parser.parse(file_path)
        chunks = self.chunker.split(file_md5, segments, user_id, org_tag, is_public)
        await self.repository.delete_by_file_md5(file_md5)
        await self.index.delete_by_file_md5(file_md5)
        if not chunks:
            await self.session.flush()
            return RagIngestionResult(0, 0, self.embedding_service.model_version)

        texts = [chunk.text_content for chunk in chunks]
        actual_embedding_tokens = sum(max(1, len(text) // 4) for text in texts)
        billing = BillingService(self.session)
        await billing.ensure_enough(int(user_id), "EMBEDDING", actual_embedding_tokens)
        vectors = await self.embedding_service.embed_texts(texts, user_id, "UPLOAD")
        await self.repository.save_chunks(chunks, self.embedding_service.model_version)
        await self.index.bulk_index(chunks, vectors)
        await billing.consume_tokens(
            user_id=int(user_id),
            token_type="EMBEDDING",
            amount=actual_embedding_tokens,
            reason="文件向量化消耗",
            remark=file_md5,
        )
        await self.session.flush()
        return RagIngestionResult(
            actual_embedding_tokens=actual_embedding_tokens,
            actual_chunk_count=len(chunks),
            model_version=self.embedding_service.model_version,
        )

    async def close(self) -> None:
        await self.index.close()

    def _select_parser(self, file_path: str) -> Parser:
        extension = Path(file_path).suffix.lower()
        if extension == ".pdf":
            return LiteParsePdfParser()
        if extension == ".docx":
            return DocxParser()
        if extension in {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm", ".css", ".js", ".py", ".java", ".sql"}:
            return PlainTextParser()
        if extension == ".doc":
            raise RuntimeError("暂不支持直接解析 .doc，请转换为 .docx 后上传")
        return PlainTextParser()
