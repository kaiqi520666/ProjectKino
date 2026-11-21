from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

CANVAS_STATUSES = ("active", "archived")
USER_ASSET_KINDS = ("text", "image", "video", "audio")
USER_ASSET_SOURCES = ("canvas", "studio", "upload")


class Canvas(TimestampMixin, Base):
    __tablename__ = "canvases"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="canvas_status_allowed"),
        CheckConstraint("schema_version >= 1", name="canvas_schema_version_positive"),
        CheckConstraint("version >= 1", name="canvas_version_positive"),
        CheckConstraint("node_count >= 0", name="canvas_node_count_nonnegative"),
        Index("ix_canvases_user_status_updated", "user_id", "status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    cover_key: Mapped[str | None] = mapped_column(String(512))
    cover_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    node_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    viewport: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    graph_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{\"nodes\": [], \"edges\": []}'::jsonb"),
    )


class UserAsset(TimestampMixin, Base):
    __tablename__ = "user_assets"
    __table_args__ = (
        CheckConstraint("kind IN ('text', 'image', 'video', 'audio')", name="user_asset_kind_allowed"),
        CheckConstraint(
            "source_type IN ('canvas', 'studio', 'upload')",
            name="user_asset_source_allowed",
        ),
        Index("ix_user_assets_user_kind_created", "user_id", "kind", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    text_content: Mapped[str | None] = mapped_column(Text)
    media_key: Mapped[str | None] = mapped_column(String(512))
    media_url: Mapped[str | None] = mapped_column(Text)
    media_name: Mapped[str | None] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="canvas")
    source_id: Mapped[UUID | None] = mapped_column()
