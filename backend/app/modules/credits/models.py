from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CreditReservation(TimestampMixin, Base):
    """图片与视频任务的预冻结凭证；LLM 不走预冻结。"""

    __tablename__ = "credit_reservations"
    __table_args__ = (
        UniqueConstraint("business_type", "business_id", name="uq_credit_reservations_business"),
        CheckConstraint("business_type IN ('image', 'video')", name="business_type_allowed"),
        CheckConstraint("status IN ('frozen', 'settled', 'released')", name="status_allowed"),
        CheckConstraint("amount >= 0", name="amount_nonnegative"),
        CheckConstraint(
            "(status = 'frozen' AND consumed IS NULL) OR "
            "(status = 'settled' AND consumed IS NOT NULL AND consumed >= 0) OR "
            "(status = 'released' AND consumed IS NOT NULL AND consumed = 0)",
            name="consumed_valid",
        ),
        Index("ix_credit_reservations_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    business_type: Mapped[str] = mapped_column(String(8), nullable=False)
    business_id: Mapped[UUID] = mapped_column(nullable=False)
    model_id: Mapped[str] = mapped_column(String(48), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    consumed: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="frozen")
    rate_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class CreditLedger(TimestampMixin, Base):
    """不可篡改的积分全量流水；支持 DeepSeek 事后扣成负数。"""

    __tablename__ = "credit_ledgers"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_credit_ledgers_idempotency_key"),
        CheckConstraint(
            "operation IN ('grant', 'freeze', 'settle', 'release', 'llm_consume', 'adjust')",
            name="operation_allowed",
        ),
        CheckConstraint("frozen_before >= 0 AND frozen_after >= 0", name="frozen_nonnegative"),
        CheckConstraint(
            "balance_after = balance_before + balance_change AND "
            "frozen_after = frozen_before + frozen_change",
            name="changes_balanced",
        ),
        Index("ix_credit_ledgers_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    operator_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    reservation_id: Mapped[UUID | None] = mapped_column(ForeignKey("credit_reservations.id"))
    job_id: Mapped[UUID | None] = mapped_column()
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    balance_change: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    frozen_change: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    frozen_before: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    frozen_after: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
