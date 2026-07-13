import asyncio
import hashlib
import math
import shutil
from urllib.parse import quote
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import ApiError
from app.core.config import settings
from app.core.redis import redis_client
from app.integrations.kafka_client import KafkaTaskProducer
from app.integrations.minio_storage import MinioStorage
from app.models.file_upload import ChunkInfo, FileUpload
from app.models.user import User
from app.repositories.file_upload_repository import FileUploadRepository
from app.repositories.organization_tag_repository import OrganizationTagRepository
from app.services.permission_service import PermissionService
from app.workers.schemas import FileProcessingTask

CHUNK_SIZE_BYTES = 5 * 1024 * 1024
SUPPORTED_EXTENSIONS = {"pdf", "doc", "docx", "txt"}


class FileUploadService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = FileUploadRepository(session)
        self.organization_tags = OrganizationTagRepository(session)
        self.storage = MinioStorage()
        self.local_root = Path(settings.upload_storage_dir)
        self.producer = KafkaTaskProducer()
        self.permissions = PermissionService()

    async def upload_chunk(
        self,
        *,
        current_user: User,
        file_md5: str,
        chunk_index: int,
        total_size: int,
        file_name: str,
        org_tag: str | None,
        is_public: bool,
        file: UploadFile,
    ) -> dict[str, object]:
        self._validate_upload_request(file_md5, chunk_index, total_size, file_name)
        user_id = str(current_user.id)
        resolved_org_tag = org_tag or current_user.primary_org
        if not self.permissions.can_upload_to_org(current_user, resolved_org_tag):
            raise ApiError(403, "No permission to upload to this organization tag")
        await self._validate_org_upload_limit(
            current_user=current_user,
            org_tag=resolved_org_tag,
            total_size=total_size,
        )
        upload = await self.repository.ensure_upload(
            file_md5=file_md5,
            file_name=file_name,
            total_size=total_size,
            user_id=user_id,
            org_tag=resolved_org_tag,
            is_public=is_public,
        )
        if upload.status == FileUpload.STATUS_MERGING:
            raise ApiError(409, "File is merging, retry later")
        if upload.status == FileUpload.STATUS_COMPLETED:
            raise ApiError(409, "File has already been merged")

        chunk_bytes = await file.read()
        chunk_md5 = hashlib.md5(chunk_bytes).hexdigest()
        object_name = self._chunk_storage_path(file_md5, chunk_index)
        temp_path = self.local_root / "tmp" / file_md5 / str(chunk_index)
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_bytes(chunk_bytes)
        await asyncio.to_thread(self.storage.put_file, object_name, temp_path, file.content_type)
        temp_path.unlink(missing_ok=True)

        await self.repository.save_chunk(
            ChunkInfo(
                file_md5=file_md5,
                chunk_index=chunk_index,
                chunk_md5=chunk_md5,
                storage_path=object_name,
            )
        )
        await self._mark_chunk_uploaded(user_id, file_md5, chunk_index)
        await self.session.commit()
        return await self.get_upload_status(file_md5=file_md5, current_user=current_user)

    async def get_upload_status(self, *, file_md5: str, current_user: User) -> dict[str, object]:
        user_id = str(current_user.id)
        upload = await self.repository.get_by_file_md5_and_user(file_md5, user_id)
        uploaded = await self.repository.list_chunk_indexes(file_md5)
        total_chunks = self._total_chunks(upload.total_size if upload else 0)
        progress = self._calculate_progress(len(uploaded), total_chunks)
        return {
            "uploaded": uploaded,
            "progress": progress,
            "totalChunks": total_chunks,
            "fileName": upload.file_name if upload else "unknown",
            "fileType": self._file_type(upload.file_name) if upload else "unknown",
        }

    async def merge_file(
        self,
        *,
        current_user: User,
        file_md5: str,
        file_name: str,
    ) -> dict[str, object]:
        user_id = str(current_user.id)
        upload = await self.repository.get_by_file_md5_and_user(file_md5, user_id)
        if upload is None:
            raise ApiError(404, "File upload record does not exist")
        if upload.status == FileUpload.STATUS_COMPLETED:
            return self._merge_response(file_md5)
        if upload.status == FileUpload.STATUS_MERGING:
            raise ApiError(409, "File is merging, retry later")

        chunks = await self.repository.list_chunks(file_md5)
        total_chunks = self._total_chunks(upload.total_size)
        if len(chunks) < total_chunks:
            raise ApiError(400, "File chunks are incomplete")

        upload.status = FileUpload.STATUS_MERGING
        await self.session.flush()

        merged_object = self._merged_storage_path(file_md5)
        try:
            for chunk in chunks:
                exists = await asyncio.to_thread(self.storage.object_exists, chunk.storage_path)
                if not exists:
                    raise ApiError(400, f"Chunk {chunk.chunk_index} does not exist")
            await asyncio.to_thread(
                self.storage.compose,
                merged_object,
                [chunk.storage_path for chunk in chunks],
            )
            upload.status = FileUpload.STATUS_COMPLETED
            upload.file_name = file_name
            upload.merged_at = datetime.now()
            upload.vectorization_status = FileUpload.VECTORIZATION_STATUS_PROCESSING
            upload.vectorization_error_message = None
            upload.estimated_embedding_tokens = self._estimate_embedding_tokens(upload.total_size)
            upload.estimated_chunk_count = max(1, math.ceil(upload.total_size / CHUNK_SIZE_BYTES))
            await self.repository.delete_chunks(file_md5)
            await self._delete_upload_bitmap(user_id, file_md5)
            await self.session.commit()
            await self._remove_chunk_objects(chunks)
            self._cleanup_local_tmp(file_md5)
        except Exception:
            upload.status = FileUpload.STATUS_UPLOADING
            await self.session.commit()
            raise
        try:
            await self.enqueue_processing_task(upload, merged_object)
        except Exception as exception:
            await self.repository.mark_vectorization_failed(file_md5, f"Kafka task publish failed: {exception}")
            await self.session.commit()
        return self._merge_response(
            file_md5,
            estimated_embedding_tokens=upload.estimated_embedding_tokens,
            estimated_chunk_count=upload.estimated_chunk_count,
        )

    async def list_user_uploads(self, current_user: User) -> list[dict[str, object]]:
        uploads = await self.repository.list_user_uploads(str(current_user.id))
        return [self.to_upload_response(upload) for upload in uploads]

    async def list_accessible_uploads(self, current_user: User) -> list[dict[str, object]]:
        uploads = await self.repository.list_accessible(
            user_id=str(current_user.id),
            org_tags=current_user.org_tag_list,
            is_admin=current_user.role == "ADMIN",
        )
        return [self.to_upload_response(upload) for upload in uploads]

    async def delete_document(self, *, current_user: User, file_md5: str) -> None:
        upload = await self.repository.get_by_file_md5(file_md5)
        if upload is None:
            raise ApiError(404, "Document does not exist")
        if not self.permissions.can_delete_document(current_user, upload):
            raise ApiError(403, "No permission to delete this document")
        chunks = await self.repository.list_chunks(file_md5)
        await self.repository.delete_chunks(file_md5)
        await self.repository.delete_upload(upload)
        await self.session.commit()
        for chunk in chunks:
            await asyncio.to_thread(self._remove_object_quietly, chunk.storage_path)
        await asyncio.to_thread(self._remove_object_quietly, self._merged_storage_path(file_md5))
        self._cleanup_local_tmp(file_md5)

    async def get_accessible_upload(self, *, current_user: User, file_md5: str) -> FileUpload:
        upload = await self.repository.get_by_file_md5(file_md5)
        if upload and self.permissions.can_access_document(current_user, upload):
            return upload
        raise ApiError(404, "Document does not exist or is not accessible")

    async def download_merged_file(self, file_md5: str, file_name: str | None = None) -> Path:
        suffix = Path(file_name or file_md5).suffix
        target = self.local_root / "downloads" / f"{file_md5}{suffix}"
        return await asyncio.to_thread(
            self.storage.download_file,
            self._merged_storage_path(file_md5),
            target,
        )

    async def build_preview_payload(
        self,
        upload: FileUpload,
        page_number: int | None = None,
    ) -> dict[str, object]:
        extension = self._extension(upload.file_name)
        preview_type = self._preview_type(extension)
        payload: dict[str, object] = {
            "fileName": upload.file_name,
            "fileMd5": upload.file_md5,
            "fileSize": upload.total_size,
            "previewType": preview_type,
        }
        if preview_type == "text":
            path = await self.download_merged_file(upload.file_md5, upload.file_name)
            payload["content"] = path.read_text(encoding="utf-8", errors="replace")
            return payload
        payload["previewUrl"] = self._file_access_url(upload.file_md5, upload.file_name, disposition="inline")
        if preview_type == "pdf" and page_number and page_number > 0:
            payload["sourceUrl"] = payload["previewUrl"]
            payload["singlePageMode"] = False
        return payload

    def build_download_payload(self, upload: FileUpload) -> dict[str, object]:
        return {
            "fileName": upload.file_name,
            "downloadUrl": self._file_access_url(upload.file_md5, upload.file_name, disposition="attachment"),
            "fileSize": upload.total_size,
            "fileMd5": upload.file_md5,
        }

    def to_upload_response(self, upload: FileUpload) -> dict[str, object]:
        total_chunks = self._total_chunks(upload.total_size)
        progress = 100 if upload.status == FileUpload.STATUS_COMPLETED else 0
        return {
            "id": upload.id,
            "fileMd5": upload.file_md5,
            "fileName": upload.file_name,
            "totalSize": upload.total_size,
            "status": upload.status,
            "userId": upload.user_id,
            "orgTag": upload.org_tag,
            "orgTagName": upload.org_tag,
            "public": upload.is_public,
            "isPublic": upload.is_public,
            "uploadedChunks": list(range(total_chunks)) if progress == 100 else [],
            "progress": progress,
            "createdAt": upload.created_at.isoformat() if upload.created_at else None,
            "mergedAt": upload.merged_at.isoformat() if upload.merged_at else None,
            "estimatedEmbeddingTokens": upload.estimated_embedding_tokens,
            "estimatedChunkCount": upload.estimated_chunk_count,
            "actualEmbeddingTokens": upload.actual_embedding_tokens,
            "actualChunkCount": upload.actual_chunk_count,
            "vectorizationStatus": upload.vectorization_status,
            "vectorizationErrorMessage": upload.vectorization_error_message,
        }

    async def enqueue_processing_task(self, upload: FileUpload, merged_object: str) -> None:
        task = FileProcessingTask(
            file_md5=upload.file_md5,
            file_path=merged_object,
            file_name=upload.file_name,
            user_id=upload.user_id,
            org_tag=upload.org_tag,
            is_public=upload.is_public,
            task_type="UPLOAD_PROCESS",
            requester_id=upload.user_id,
        )
        await self.producer.send_file_processing_task(task)

    async def _remove_chunk_objects(self, chunks: list[ChunkInfo]) -> None:
        for chunk in chunks:
            await asyncio.to_thread(self._remove_object_quietly, chunk.storage_path)

    def _remove_object_quietly(self, object_name: str) -> None:
        try:
            self.storage.remove_object(object_name)
        except Exception:
            pass

    def _validate_upload_request(
        self,
        file_md5: str,
        chunk_index: int,
        total_size: int,
        file_name: str,
    ) -> None:
        if len(file_md5) != 32 or any(char not in "0123456789abcdefABCDEF" for char in file_md5):
            raise ApiError(400, "Invalid file MD5")
        if chunk_index < 0:
            raise ApiError(400, "chunkIndex must be non-negative")
        if total_size <= 0:
            raise ApiError(400, "totalSize must be positive")
        extension = self._extension(file_name)
        if extension not in SUPPORTED_EXTENSIONS:
            raise ApiError(400, f"Unsupported file type: {extension or 'unknown'}")

    async def _validate_org_upload_limit(self, *, current_user: User, org_tag: str | None, total_size: int) -> None:
        if current_user.role == "ADMIN" or not org_tag:
            return
        tag = await self.organization_tags.find_by_tag_id(org_tag)
        if tag is None or tag.upload_max_size_bytes is None:
            return
        if total_size > tag.upload_max_size_bytes:
            raise ApiError(400, "File size exceeds organization upload limit")

    async def _mark_chunk_uploaded(self, user_id: str, file_md5: str, chunk_index: int) -> None:
        await redis_client.setbit(self._upload_bitmap_key(user_id, file_md5), chunk_index, 1)

    async def _delete_upload_bitmap(self, user_id: str, file_md5: str) -> None:
        await redis_client.delete(self._upload_bitmap_key(user_id, file_md5))

    def _chunk_storage_path(self, file_md5: str, chunk_index: int) -> str:
        return f"chunks/{file_md5}/{chunk_index}"

    def _merged_storage_path(self, file_md5: str) -> str:
        return f"merged/{file_md5}"

    def _cleanup_local_tmp(self, file_md5: str) -> None:
        shutil.rmtree(self.local_root / "tmp" / file_md5, ignore_errors=True)

    def _download_url(self, file_md5: str) -> str:
        return f"/api/v1/documents/download-by-md5?fileMd5={file_md5}"

    def _file_access_url(self, file_md5: str, file_name: str, disposition: str) -> str:
        encoded_name = quote(file_name)
        return self.storage.presigned_get_url(
            self._merged_storage_path(file_md5),
            response_headers={
                "response-content-disposition": f"{disposition}; filename*=UTF-8''{encoded_name}",
            },
        )

    def _merge_response(
        self,
        file_md5: str,
        estimated_embedding_tokens: int | None = None,
        estimated_chunk_count: int | None = None,
    ) -> dict[str, object]:
        object_url = self._download_url(file_md5)
        return {
            "object_url": object_url,
            "objectUrl": object_url,
            "estimatedEmbeddingTokens": estimated_embedding_tokens,
            "estimatedChunkCount": estimated_chunk_count,
        }

    def _calculate_progress(self, uploaded_count: int, total_chunks: int) -> float:
        if total_chunks == 0:
            return 0.0
        return round(uploaded_count / total_chunks * 100, 2)

    def _total_chunks(self, total_size: int) -> int:
        if total_size <= 0:
            return 0
        return math.ceil(total_size / CHUNK_SIZE_BYTES)

    def _estimate_embedding_tokens(self, total_size: int) -> int:
        return max(1, math.ceil(total_size / 4))

    def _extension(self, file_name: str) -> str:
        return Path(file_name).suffix.lower().lstrip(".")

    def _file_type(self, file_name: str) -> str:
        extension = self._extension(file_name)
        return extension.upper() + " file" if extension else "unknown"

    def _preview_type(self, extension: str) -> str:
        if extension == "pdf":
            return "pdf"
        if extension in {"png", "jpg", "jpeg", "gif", "bmp", "webp", "svg"}:
            return "image"
        if extension in {"txt", "md", "json", "xml", "csv", "html", "htm", "css", "js", "py", "java", "sql"}:
            return "text"
        return "download"

    def _upload_bitmap_key(self, user_id: str, file_md5: str) -> str:
        return f"upload:{user_id}:{file_md5}"
