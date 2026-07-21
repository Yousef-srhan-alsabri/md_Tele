from datetime import datetime
from enum import Enum
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class LinkStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    JOINED = "joined"
    REQUESTED = "requested"
    ALREADY_MEMBER = "already_member"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"
    CANCELLED = "cancelled"

class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delay_seconds: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    rest_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    accounts: Mapped[list["TelegramAccount"]] = relationship(back_populates="user", cascade="all, delete-orphan")

class TelegramAccount(Base):
    __tablename__ = "telegram_accounts"
    __table_args__ = (UniqueConstraint("user_id", "phone", name="uq_user_phone"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    phone: Mapped[str] = mapped_column(String(32))
    encrypted_session: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped[User] = relationship(back_populates="accounts")

class Link(Base):
    __tablename__ = "links"
    __table_args__ = (UniqueConstraint("user_id", "value", name="uq_user_link"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    value: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default=LinkStatus.PENDING.value, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("telegram_accounts.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.QUEUED.value, index=True)
    stop_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class BalanceTransaction(Base):
    __tablename__ = "balance_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))
    link_id: Mapped[int | None] = mapped_column(ForeignKey("links.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
