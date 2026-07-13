from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column("conversation_id", String(64), index=True)
    reference_mappings_json: Mapped[str | None] = mapped_column(
        "reference_mappings_json",
        Text,
        nullable=True,
    )
    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime,
        server_default=func.now(),
        index=True,
    )


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(
        "conversation_id",
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", index=True)
    created_at: Mapped[datetime | None] = mapped_column(
        "created_at",
        DateTime,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        "updated_at",
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )
