from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_vector import DocumentVector
from app.rag.schemas import TextChunk


class DocumentVectorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_file_md5(self, file_md5: str) -> list[DocumentVector]:
        result = await self.session.execute(
            select(DocumentVector)
            .where(DocumentVector.file_md5 == file_md5)
            .order_by(DocumentVector.chunk_id.asc())
        )
        return list(result.scalars().all())

    async def delete_by_file_md5(self, file_md5: str) -> None:
        await self.session.execute(delete(DocumentVector).where(DocumentVector.file_md5 == file_md5))

    async def save_chunks(self, chunks: list[TextChunk], model_version: str | None = None) -> None:
        self.session.add_all(
            [
                DocumentVector(
                    file_md5=chunk.file_md5,
                    chunk_id=chunk.chunk_id,
                    text_content=chunk.text_content,
                    page_number=chunk.page_number,
                    anchor_text=chunk.anchor_text,
                    model_version=model_version,
                    user_id=chunk.user_id,
                    org_tag=chunk.org_tag,
                    is_public=chunk.is_public,
                )
                for chunk in chunks
            ]
        )
        await self.session.flush()
