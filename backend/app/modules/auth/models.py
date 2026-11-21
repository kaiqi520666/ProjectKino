from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Identity, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'operator', 'admin')", name="role_allowed"),
        CheckConstraint("status IN ('active', 'disabled')", name="status_allowed"),
        CheckConstraint("frozen >= 0", name="frozen_nonnegative"),
        CheckConstraint("usage_multiplier > 0", name="multiplier_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    nickname: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default="user")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    # LLM 按真实返回 token 事后扣费，允许 balance 扣成负数；仅 frozen 必须 >= 0。
    balance: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default="0.0000")
    frozen: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default="0.0000")
    usage_multiplier: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, server_default="1.0000")
