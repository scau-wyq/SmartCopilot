from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FileUpload(Base):
    __tablename__ = "file_upload"
    __table_args__ = (
        UniqueConstraint("file_md5", "user_id", name="uk_file_upload_md5_user"),
    )

    STATUS_UPLOADING = 0
    STATUS_COMPLETED = 1
    STATUS_MERGING = 2

    VECTORIZATION_STATUS_PENDING = "PENDING"
    VECTORIZATION_STATUS_PROCESSING = "PROCESSING"
    VECTORIZATION_STATUS_COMPLETED = "COMPLETED"
    VECTORIZATION_STATUS_FAILED = "FAILED"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file_md5: Mapped[str] = mapped_column("file_md5", String(32), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column("file_name", String(255), nullable=False)
    total_size: Mapped[int] = mapped_column("total_size", BigInteger, nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=STATUS_UPLOADING)
    user_id: Mapped[str] = mapped_column("user_id", String(64), nullable=False, index=True)
    org_tag: Mapped[str | None] = mapped_column("org_tag", String(255), nullable=True, index=True)
    is_public: Mapped[bool] = mapped_column("is_public", Boolean, nullable=False, default=False)
    estimated_embedding_tokens: Mapped[int | None] = mapped_column(
        "estimated_embedding_tokens",
        BigInteger,
        nullable=True,
    )
    estimated_chunk_count: Mapped[int | None] = mapped_column(
        "estimated_chunk_count",
        Integer,
        nullable=True,
    )
    actual_embedding_tokens: Mapped[int | None] = mapped_column(
        "actual_embedding_tokens",
        BigInteger,
        nullable=True,
    )
    actual_chunk_count: Mapped[int | None] = mapped_column(
        "actual_chunk_count",
        Integer,
        nullable=True,
    )
    vectorization_status: Mapped[str | None] = mapped_column(
        "vectorization_status",
        String(32),
        nullable=True,
    )
    vectorization_error_message: Mapped[str | None] = mapped_column(
        "vectorization_error_message",
        String(1000),
        nullable=True,
    )
    created_at: Mapped[datetime | None] = mapped_column(
        "created_at",
        DateTime,
        server_default=func.now(),
    )
    merged_at: Mapped[datetime | None] = mapped_column(
        "merged_at",
        DateTime,
        nullable=True,
        onupdate=func.now(),
    )


class ChunkInfo(Base):
    __tablename__ = "chunk_info"
    __table_args__ = (
        UniqueConstraint("file_md5", "chunk_index", name="uk_file_md5_chunk_index"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file_md5: Mapped[str] = mapped_column("file_md5", String(32), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column("chunk_index", Integer, nullable=False)
    chunk_md5: Mapped[str] = mapped_column("chunk_md5", String(32), nullable=False)
    storage_path: Mapped[str] = mapped_column("storage_path", String(255), nullable=False)
