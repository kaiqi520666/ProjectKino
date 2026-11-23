from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("mode IN ('story', 'upload')", name="mode_allowed"),
        CheckConstraint("status IN ('active', 'archived')", name="status_allowed"),
        Index("ix_projects_user_updated", "user_id", "updated_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default="story")
    source_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    outline: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    script_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")


class Episode(TimestampMixin, Base):
    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint("project_id", "number", name="uq_episodes_project_number"),
        CheckConstraint("number >= 1", name="number_positive"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    target_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="120")
    seconds: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    hook: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    cliff: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    hook_beat: Mapped[list[int]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[1, 1]'::jsonb")
    )
    # 唯一事实来源：结构化场次与节拍流。
    scenes: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    # 由 scenes 派生的展示正文缓存。
    script: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    composed_video_key: Mapped[str | None] = mapped_column(Text)
    composed_video_url: Mapped[str | None] = mapped_column(Text)
    composed_duration: Mapped[float | None] = mapped_column(Float)


class ProjectAsset(TimestampMixin, Base):
    __tablename__ = "project_assets"
    __table_args__ = (
        UniqueConstraint("project_id", "asset_code", name="uq_project_assets_code"),
        CheckConstraint("kind IN ('character', 'scene', 'prop')", name="kind_allowed"),
        CheckConstraint(
            "image_status IN ('none', 'generating', 'ready', 'failed')",
            name="image_status_allowed",
        ),
        CheckConstraint(
            "image_tier IS NULL OR image_tier IN ('web', '1k', '2k', '4k')",
            name="image_tier_allowed",
        ),
        CheckConstraint(
            "parent_asset_id IS NULL OR parent_asset_id <> id",
            name="parent_not_self",
        ),
        Index("ix_project_assets_parent_id", "parent_asset_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("project_assets.id", ondelete="SET NULL"), nullable=True
    )
    variant_label: Mapped[str] = mapped_column(String(48), nullable=False, default="", server_default="")
    asset_code: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    voice: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    episode_numbers: Mapped[list[int]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    image_key: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    image_model_id: Mapped[str | None] = mapped_column(String(48))
    image_tier: Mapped[str | None] = mapped_column(String(8))
    image_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="none")
    image_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    last_job_id: Mapped[UUID | None] = mapped_column()


class StoryboardClip(TimestampMixin, Base):
    __tablename__ = "storyboard_clips"
    __table_args__ = (
        UniqueConstraint("episode_id", "clip_index", name="uq_storyboard_clips_episode_index"),
        CheckConstraint("clip_index >= 1", name="clip_index_positive"),
        CheckConstraint("duration_seconds >= 1", name="duration_positive"),
        CheckConstraint(
            "video_status IN ('none', 'generating', 'ready', 'failed')",
            name="video_status_allowed",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    episode_id: Mapped[UUID] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clip_index: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    prompt_customized: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    beats: Mapped[list[int] | None] = mapped_column(JSONB)
    blocking: Mapped[str | None] = mapped_column(Text)
    cuts: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    preview_key: Mapped[str | None] = mapped_column(Text)
    preview_url: Mapped[str | None] = mapped_column(Text)
    video_key: Mapped[str | None] = mapped_column(Text)
    video_url: Mapped[str | None] = mapped_column(Text)
    video_model_id: Mapped[str | None] = mapped_column(String(48))
    video_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="none")
    video_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    last_job_id: Mapped[UUID | None] = mapped_column()
