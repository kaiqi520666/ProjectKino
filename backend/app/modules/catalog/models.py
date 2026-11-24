from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AiProvider(TimestampMixin, Base):
    __tablename__ = "ai_providers"
    __table_args__ = (CheckConstraint("auth_type IN ('bearer', 'apiKey')", name="auth_type_allowed"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key: Mapped[str] = mapped_column(Text, nullable=False, deferred=True, server_default="")
    adapter: Mapped[str] = mapped_column(String(64), nullable=False)
    auth_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="bearer")
    auth_header: Mapped[str | None] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class AiModel(TimestampMixin, Base):
    __tablename__ = "ai_models"
    __table_args__ = (
        CheckConstraint("media_type IN ('text', 'image', 'video')", name="media_type_allowed"),
        CheckConstraint("NOT is_default OR enabled", name="default_enabled"),
        CheckConstraint(
            "NOT is_default_long OR (enabled AND media_type = 'video')",
            name="default_long_video_enabled",
        ),
        Index(
            "uq_ai_models_default_media",
            "media_type",
            unique=True,
            postgresql_where=text("is_default"),
        ),
        Index(
            "uq_ai_models_default_video_long",
            "media_type",
            unique=True,
            postgresql_where=text("is_default_long"),
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    provider_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ai_providers.id"), nullable=False, index=True
    )
    media_type: Mapped[str] = mapped_column(String(8), nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False, server_default="")
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    upstream_model_id: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    upstream_available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_default_long: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    defaults: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    parameter_bindings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class TextModelPrice(TimestampMixin, Base):
    """DeepSeek 按真实 Token 计费单价（每百万 Token 折算积分）。"""

    __tablename__ = "text_model_prices"
    __table_args__ = (
        CheckConstraint("input_price_per_million >= 0", name="input_nonnegative"),
        CheckConstraint("cached_input_price_per_million >= 0", name="cached_nonnegative"),
        CheckConstraint("output_price_per_million >= 0", name="output_nonnegative"),
    )

    model_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("ai_models.id", ondelete="CASCADE"), primary_key=True
    )
    input_price_per_million: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, server_default="0"
    )
    cached_input_price_per_million: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, server_default="0"
    )
    output_price_per_million: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, server_default="0"
    )


class ImageModelPrice(TimestampMixin, Base):
    """沧元图片按张 + 分辨率档位计费（web / 1k / 2k / 4k）。"""

    __tablename__ = "image_model_prices"
    __table_args__ = (
        UniqueConstraint("model_id", "tier", name="uq_image_model_prices_model_tier"),
        CheckConstraint("tier IN ('web', '1k', '2k', '4k')", name="tier_allowed"),
        CheckConstraint("credit_price >= 0", name="price_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    model_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("ai_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tier: Mapped[str] = mapped_column(String(8), nullable=False)
    credit_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)


class VideoModelPrice(TimestampMixin, Base):
    """CC 视频按秒或按条计费。"""

    __tablename__ = "video_model_prices"
    __table_args__ = (
        UniqueConstraint("model_id", "rule_key", name="uq_video_model_prices_model_rule"),
        CheckConstraint("unit IN ('second', 'call')", name="unit_allowed"),
        CheckConstraint("credit_price >= 0", name="price_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    model_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("ai_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_key: Mapped[str] = mapped_column(String(64), nullable=False, server_default="default")
    unit: Mapped[str] = mapped_column(String(16), nullable=False, server_default="second")
    credit_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)


class AiModelSyncLog(Base):
    """上游模型可用性变动记录（仅在模型上下架/恢复时写入）。"""

    __tablename__ = "ai_model_sync_logs"
    __table_args__ = (
        CheckConstraint("event_type IN ('offline', 'restored')", name="sync_event_type_allowed"),
        Index("ix_ai_model_sync_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    upstream_model_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
