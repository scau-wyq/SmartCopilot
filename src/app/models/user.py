from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(Enum("USER", "ADMIN"), nullable=False, default="USER")
    org_tags: Mapped[str | None] = mapped_column("org_tags", String(1000), nullable=True)
    primary_org: Mapped[str | None] = mapped_column("primary_org", String(255), nullable=True)
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

    @property
    def org_tag_list(self) -> list[str]:
        if not self.org_tags:
            return []
        return [item.strip() for item in self.org_tags.split(",") if item.strip()]
