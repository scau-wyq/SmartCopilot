from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserTokenRecord(Base):
    __tablename__ = "user_token_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column("user_id", Integer, ForeignKey("users.id"), nullable=False)
    record_date: Mapped[date] = mapped_column("record_date", Date, nullable=False)
    token_type: Mapped[str] = mapped_column(Enum("LLM", "EMBEDDING"), nullable=False)
    change_type: Mapped[str] = mapped_column(Enum("INCREASE", "CONSUME"), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_before: Mapped[int | None] = mapped_column("balance_before", BigInteger, nullable=True)
    balance_after: Mapped[int | None] = mapped_column("balance_after", BigInteger, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_count: Mapped[int] = mapped_column("request_count", Integer, nullable=False, default=1)
    created_at: Mapped[datetime | None] = mapped_column(
        "created_at",
        DateTime,
        server_default=func.now(),
    )


class RechargePackage(Base):
    __tablename__ = "recharge_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_name: Mapped[str] = mapped_column("package_name", String(100), nullable=False)
    package_price: Mapped[int] = mapped_column("package_price", BigInteger, nullable=False)
    package_desc: Mapped[str | None] = mapped_column("package_desc", Text, nullable=True)
    package_benefit: Mapped[str | None] = mapped_column("package_benefit", Text, nullable=True)
    llm_token: Mapped[int] = mapped_column("llm_token", BigInteger, nullable=False, default=0)
    embedding_token: Mapped[int] = mapped_column("embedding_token", BigInteger, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column("sort_order", Integer, nullable=False, default=0)
    created_at: Mapped[datetime | None] = mapped_column("created_at", DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        "updated_at",
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RechargeOrder(Base):
    __tablename__ = "recharge_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trade_no: Mapped[str] = mapped_column("trade_no", String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column("user_id", Integer, ForeignKey("users.id"), nullable=False)
    package_id: Mapped[int | None] = mapped_column("package_id", Integer, nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    llm_token: Mapped[int] = mapped_column("llm_token", BigInteger, nullable=False, default=0)
    embedding_token: Mapped[int] = mapped_column("embedding_token", BigInteger, nullable=False, default=0)
    wx_transaction_id: Mapped[str | None] = mapped_column("wx_transaction_id", String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("NOT_PAY", "PAYING", "SUCCEED", "FAIL", "CANCELLED"),
        nullable=False,
        default="NOT_PAY",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    pay_time: Mapped[datetime | None] = mapped_column("pay_time", DateTime, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column("created_at", DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        "updated_at",
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserModelPreference(Base):
    __tablename__ = "user_model_preferences"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column("user_id", Integer, ForeignKey("users.id"), unique=True, nullable=False)
    model_mode: Mapped[str] = mapped_column(
        "model_mode",
        Enum("FREE", "PAID", "CUSTOM"),
        nullable=False,
        default="FREE",
    )
    custom_base_url: Mapped[str | None] = mapped_column("custom_base_url", String(500), nullable=True)
    custom_model: Mapped[str | None] = mapped_column("custom_model", String(255), nullable=True)
    custom_api_key_encrypted: Mapped[str | None] = mapped_column(
        "custom_api_key_encrypted",
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime | None] = mapped_column("created_at", DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        "updated_at",
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )
