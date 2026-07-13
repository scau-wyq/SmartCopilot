from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file_upload import ChunkInfo, FileUpload


class FileUploadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_file_md5(self, file_md5: str) -> FileUpload | None:
        result = await self.session.execute(
            select(FileUpload)
            .where(FileUpload.file_md5 == file_md5)
            .order_by(FileUpload.created_at.desc(), FileUpload.id.desc())
        )
        return result.scalars().first()

    async def get_by_file_md5_and_user(self, file_md5: str, user_id: str) -> FileUpload | None:
        result = await self.session.execute(
            select(FileUpload)
            .where(FileUpload.file_md5 == file_md5, FileUpload.user_id == user_id)
            .order_by(FileUpload.created_at.desc(), FileUpload.id.desc())
        )
        return result.scalars().first()

    async def list_by_file_md5s(self, file_md5s: list[str]) -> list[FileUpload]:
        if not file_md5s:
            return []
        result = await self.session.execute(select(FileUpload).where(FileUpload.file_md5.in_(file_md5s)))
        return list(result.scalars().all())

    async def ensure_upload(
        self,
        *,
        file_md5: str,
        file_name: str,
        total_size: int,
        user_id: str,
        org_tag: str | None,
        is_public: bool,
    ) -> FileUpload:
        await self.session.execute(
            text(
                """
                INSERT IGNORE INTO file_upload
                    (file_md5, file_name, total_size, status, user_id, org_tag, is_public,
                     vectorization_status, created_at, merged_at)
                VALUES
                    (:file_md5, :file_name, :total_size, :status, :user_id, :org_tag,
                     :is_public, :vectorization_status, NOW(), NOW())
                """
            ),
            {
                "file_md5": file_md5,
                "file_name": file_name,
                "total_size": total_size,
                "status": FileUpload.STATUS_UPLOADING,
                "user_id": user_id,
                "org_tag": org_tag,
                "is_public": is_public,
                "vectorization_status": None,
            },
        )
        upload = await self.get_by_file_md5_and_user(file_md5, user_id)
        if upload is None:
            raise RuntimeError("File upload record was not created")
        return upload

    async def save_chunk(self, chunk: ChunkInfo) -> None:
        await self.session.execute(
            text(
                """
                INSERT IGNORE INTO chunk_info
                    (file_md5, chunk_index, chunk_md5, storage_path)
                VALUES
                    (:file_md5, :chunk_index, :chunk_md5, :storage_path)
                """
            ),
            {
                "file_md5": chunk.file_md5,
                "chunk_index": chunk.chunk_index,
                "chunk_md5": chunk.chunk_md5,
                "storage_path": chunk.storage_path,
            },
        )

    async def list_chunks(self, file_md5: str) -> list[ChunkInfo]:
        result = await self.session.execute(
            select(ChunkInfo)
            .where(ChunkInfo.file_md5 == file_md5)
            .order_by(ChunkInfo.chunk_index.asc())
        )
        return list(result.scalars().all())

    async def list_chunk_indexes(self, file_md5: str) -> list[int]:
        result = await self.session.execute(
            select(ChunkInfo.chunk_index)
            .where(ChunkInfo.file_md5 == file_md5)
            .order_by(ChunkInfo.chunk_index.asc())
        )
        return [int(item) for item in result.scalars().all()]

    async def delete_chunks(self, file_md5: str) -> None:
        await self.session.execute(delete(ChunkInfo).where(ChunkInfo.file_md5 == file_md5))

    async def list_user_uploads(self, user_id: str) -> list[FileUpload]:
        result = await self.session.execute(
            select(FileUpload)
            .where(FileUpload.user_id == user_id)
            .order_by(FileUpload.created_at.desc(), FileUpload.id.desc())
        )
        return list(result.scalars().all())

    async def list_accessible(
        self,
        *,
        user_id: str,
        org_tags: list[str],
        is_admin: bool,
    ) -> list[FileUpload]:
        statement = select(FileUpload)
        if not is_admin:
            conditions = [
                FileUpload.user_id == user_id,
                FileUpload.is_public.is_(True),
                FileUpload.org_tag.is_(None),
                FileUpload.org_tag == "",
                FileUpload.org_tag == "DEFAULT",
            ]
            if org_tags:
                conditions.append(FileUpload.org_tag.in_(org_tags))

            statement = statement.where(or_(*conditions))
        statement = statement.order_by(FileUpload.created_at.desc(), FileUpload.id.desc())
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def delete_upload(self, upload: FileUpload) -> None:
        await self.session.delete(upload)

    async def mark_vectorization_processing(
        self,
        file_md5: str,
        reset_actual_usage: bool = False,
    ) -> FileUpload | None:
        upload = await self.get_by_file_md5(file_md5)
        if upload is None:
            return None
        upload.vectorization_status = FileUpload.VECTORIZATION_STATUS_PROCESSING
        upload.vectorization_error_message = None
        if reset_actual_usage:
            upload.actual_embedding_tokens = None
            upload.actual_chunk_count = None
        await self.session.flush()
        return upload

    async def mark_vectorization_completed(
        self,
        file_md5: str,
        actual_embedding_tokens: int,
        actual_chunk_count: int,
    ) -> FileUpload | None:
        upload = await self.get_by_file_md5(file_md5)
        if upload is None:
            return None
        upload.vectorization_status = FileUpload.VECTORIZATION_STATUS_COMPLETED
        upload.vectorization_error_message = None
        upload.actual_embedding_tokens = actual_embedding_tokens
        upload.actual_chunk_count = actual_chunk_count
        await self.session.flush()
        return upload

    async def mark_vectorization_failed(self, file_md5: str, message: str) -> FileUpload | None:
        upload = await self.get_by_file_md5(file_md5)
        if upload is None:
            return None
        upload.vectorization_status = FileUpload.VECTORIZATION_STATUS_FAILED
        upload.vectorization_error_message = message[:1000]
        await self.session.flush()
        return upload
