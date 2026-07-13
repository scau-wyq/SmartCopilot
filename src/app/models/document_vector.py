from sqlalchemy import BigInteger, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DocumentVector(Base):
    __tablename__ = "document_vectors"

    vector_id: Mapped[int] = mapped_column("vector_id", BigInteger, primary_key=True, autoincrement=True)
    file_md5: Mapped[str] = mapped_column("file_md5", String(32), nullable=False, index=True)
    chunk_id: Mapped[int] = mapped_column("chunk_id", Integer, nullable=False)
    text_content: Mapped[str] = mapped_column("text_content", Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column("page_number", Integer, nullable=True)
    anchor_text: Mapped[str | None] = mapped_column("anchor_text", String(512), nullable=True)
    model_version: Mapped[str | None] = mapped_column("model_version", String(32), nullable=True)
    user_id: Mapped[str] = mapped_column("user_id", String(64), nullable=False, index=True)
    org_tag: Mapped[str | None] = mapped_column("org_tag", String(50), nullable=True, index=True)
    is_public: Mapped[bool] = mapped_column("is_public", Boolean, nullable=False, default=False)
