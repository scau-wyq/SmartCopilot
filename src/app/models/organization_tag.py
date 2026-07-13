from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OrganizationTag(Base):
    __tablename__ = "organization_tags"

    tag_id: Mapped[str] = mapped_column("tag_id", String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_tag: Mapped[str | None] = mapped_column("parent_tag", String(255), nullable=True, index=True)
    upload_max_size_bytes: Mapped[int | None] = mapped_column("upload_max_size_bytes", BigInteger, nullable=True)
    created_by: Mapped[int] = mapped_column("created_by", Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column("created_at", DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        "updated_at",
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )
