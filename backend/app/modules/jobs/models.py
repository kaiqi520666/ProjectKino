from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
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

JOB_TYPES = (
    "script_generate",
    "script_regenerate",
    "episode_rewrite",
    "episode_append",
    "assets_extract",
    "asset_image",
    "storyboard_generate",
    "clip_video",
    "episode_compose",
    "canvas_text",
    "canvas_image",
    "canvas_video",
)

JOB_STATUSES = ("queued", "running", "polling", "succeeded", "failed", "review")


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('script_generate', 'script_regenerate', 'episode_rewrite', "
            "'episode_append', 'assets_extract', 'asset_image', 'storyboard_generate', "
            "'clip_video', 'episode_compose', 'canvas_text', 'canvas_image', 'canvas_video')",
            name="job_type_allowed",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'polling', 'succeeded', 'failed', 'review')",
            name="status_allowed",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="progress_range"),
        CheckConstraint(
            "NOT (project_id IS NOT NULL AND canvas_id IS NOT NULL)",
            name="job_owner_exclusive",
        ),
        Index("ix_jobs_user_created", "user_id", "created_at", "id"),
        Index("ix_jobs_project_status", "project_id", "status"),
        Index("ix_jobs_canvas_status", "canvas_id", "status"),
        Index(
            "ix_jobs_dispatch_due",
            "dispatch_after",
            "next_attempt_at",
            postgresql_where=text("status IN ('queued', 'polling')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    canvas_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("canvases.id", ondelete="SET NULL"), index=True
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    step_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    step_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    step_label: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    input_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    provider_task_id: Mapped[str | None] = mapped_column(String(512))
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    usage_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
