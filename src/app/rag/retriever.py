from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.rag.embeddings import EmbeddingService
from app.rag.indexer import VectorIndex
from app.rag.schemas import SearchResult
from app.repositories.file_upload_repository import FileUploadRepository
from app.services.billing_service import BillingService


class HybridRetriever:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.embedding_service = EmbeddingService()
        self.index = VectorIndex()
        self.uploads = FileUploadRepository(session)

    async def search(self, *, query: str, top_k: int, current_user: User) -> dict[str, object]:
        normalized_query, normalized_top_k, retrieval_mode, results = await self.retrieve_results(
            query=query,
            top_k=top_k,
            current_user=current_user,
        )
        return {
            "query": normalized_query,
            "topK": normalized_top_k,
            "retrievalMode": retrieval_mode,
            "results": [self._to_response(result) for result in results],
        }

    async def retrieve_results(
        self,
        *,
        query: str,
        top_k: int,
        current_user: User,
    ) -> tuple[str, int, str, list[SearchResult]]:
        normalized_query = query.strip()
        if not normalized_query:
            return query, top_k, "EMPTY_QUERY", []

        normalized_top_k = min(max(top_k, 1), 50)
        user_id = str(current_user.id)
        is_admin = current_user.role == "ADMIN"

        try:
            vectors = await self.embedding_service.embed_texts([normalized_query], user_id, "QUERY")
            if not vectors:
                raise RuntimeError("Query embedding response is empty")
        except Exception:
            retrieval_mode = "TEXT_ONLY"
            results = await self.index.text_search(
                query=normalized_query,
                top_k=normalized_top_k,
                user_id=user_id,
                org_tags=current_user.org_tag_list,
                is_admin=is_admin,
            )
        else:
            retrieval_mode = "HYBRID"
            results = await self.index.hybrid_search(
                query=normalized_query,
                query_vector=vectors[0],
                top_k=normalized_top_k,
                user_id=user_id,
                org_tags=current_user.org_tag_list,
                is_admin=is_admin,
            )
            await BillingService(self.session).consume_tokens(
                user_id=int(current_user.id),
                token_type="EMBEDDING",
                amount=max(1, len(normalized_query) // 4),
                reason="检索查询向量化消耗",
                remark=normalized_query[:200],
            )

        await self._attach_file_names(results)
        return normalized_query, normalized_top_k, retrieval_mode, results

    async def close(self) -> None:
        await self.index.close()

    async def _attach_file_names(self, results: list[SearchResult]) -> None:
        file_md5s = list({result.file_md5 for result in results if result.file_md5})
        uploads = await self.uploads.list_by_file_md5s(file_md5s)
        md5_to_name = {upload.file_md5: upload.file_name for upload in uploads}
        for result in results:
            result.file_name = md5_to_name.get(result.file_md5)

    def _to_response(self, result: SearchResult) -> dict[str, object]:
        return {
            "fileMd5": result.file_md5,
            "chunkId": result.chunk_id,
            "textContent": result.text_content,
            "score": result.score,
            "fileName": result.file_name,
            "pageNumber": result.page_number,
            "anchorText": result.anchor_text,
            "userId": result.user_id,
            "orgTag": result.org_tag,
            "isPublic": result.is_public,
            "retrievalMode": result.retrieval_mode,
        }
