from pathlib import Path

from minio import Minio
from minio.commonconfig import ComposeSource

from app.core.config import settings


class MinioStorage:
    def __init__(self) -> None:
        self.bucket = settings.minio_upload_bucket
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put_file(self, object_name: str, file_path: Path, content_type: str | None = None) -> None:
        self.ensure_bucket()
        self.client.fput_object(
            self.bucket,
            object_name,
            str(file_path),
            content_type=content_type or "application/octet-stream",
        )

    def compose(self, object_name: str, source_objects: list[str]) -> None:
        self.ensure_bucket()
        self.client.compose_object(
            self.bucket,
            object_name,
            [ComposeSource(self.bucket, source_object) for source_object in source_objects],
        )

    def download_file(self, object_name: str, target_path: Path) -> Path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        self.client.fget_object(self.bucket, object_name, str(target_path))
        return target_path

    def remove_object(self, object_name: str) -> None:
        self.client.remove_object(self.bucket, object_name)

    def object_exists(self, object_name: str) -> bool:
        try:
            self.client.stat_object(self.bucket, object_name)
            return True
        except Exception:
            return False

    def presigned_get_url(self, object_name: str, response_headers: dict[str, str] | None = None) -> str:
        return self.client.presigned_get_object(
            self.bucket,
            object_name,
            response_headers=response_headers,
        )
