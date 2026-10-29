from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="officer")  # admin | auditor | officer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)   # e.g. DEPT-ROADS
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(24), default="contractor")  # department | contractor | beneficiary
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    merkle_root: Mapped[str] = mapped_column(String(64), unique=True)
    leaf_count: Mapped[int] = mapped_column(Integer)
    chain_tx: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    parent_token: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    sender: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    receiver: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    remaining_paise: Mapped[int] = mapped_column(BigInteger)
    purpose: Mapped[str] = mapped_column(String(256), default="")
    ts: Mapped[int] = mapped_column(BigInteger, index=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    tx_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(12), default="active")  # active|flagged|frozen|cleared
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(8), default="low")
    risk_reasons: Mapped[str] = mapped_column(Text, default="[]")
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    __table_args__ = (Index("ix_tx_sender_ts", "sender", "ts"),)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), index=True)
    level: Mapped[str] = mapped_column(String(8))
    score: Mapped[float] = mapped_column(Float)
    reasons: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|investigating|resolved|dismissed
    assignee: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    """Append-only and hash-chained, so tampering with the audit trail is detectable too."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(48))
    target: Mapped[str] = mapped_column(String(80), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    ts: Mapped[int] = mapped_column(BigInteger)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
