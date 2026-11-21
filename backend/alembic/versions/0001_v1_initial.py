"""v1 initial schema

Revision ID: 0001_v1_initial
Revises:
Create Date: 2026-11-21 01:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_v1_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("nickname", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=16), server_default="user", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("balance", sa.Numeric(precision=20, scale=4), server_default="0.0000", nullable=False),
        sa.Column("frozen", sa.Numeric(precision=20, scale=4), server_default="0.0000", nullable=False),
        sa.Column(
            "usage_multiplier", sa.Numeric(precision=10, scale=4), server_default="1.0000", nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('user', 'admin')", name="ck_users_role_allowed"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_users_status_allowed"),
        sa.CheckConstraint("frozen >= 0", name="ck_users_frozen_nonnegative"),
        sa.CheckConstraint("usage_multiplier > 0", name="ck_users_multiplier_positive"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "ai_providers",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("api_key", sa.Text(), server_default="", nullable=False),
        sa.Column("adapter", sa.String(length=64), nullable=False),
        sa.Column("auth_type", sa.String(length=16), server_default="bearer", nullable=False),
        sa.Column("auth_header", sa.String(length=64), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("configuration", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("auth_type IN ('bearer', 'apiKey')", name="ck_ai_providers_auth_type_allowed"),
        sa.UniqueConstraint("key", name="uq_ai_providers_key"),
    )

    op.create_table(
        "ai_models",
        sa.Column("id", sa.String(length=48), primary_key=True),
        sa.Column("provider_id", sa.BigInteger(), sa.ForeignKey("ai_providers.id"), nullable=False),
        sa.Column("media_type", sa.String(length=8), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("upstream_model_id", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sort", sa.Integer(), server_default="0", nullable=False),
        sa.Column("capabilities", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("defaults", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "parameter_bindings", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("configuration", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "media_type IN ('text', 'image', 'video')", name="ck_ai_models_media_type_allowed"
        ),
        sa.CheckConstraint("NOT is_default OR enabled", name="ck_ai_models_default_enabled"),
    )
    op.create_index("ix_ai_models_provider_id", "ai_models", ["provider_id"])
    op.create_index(
        "uq_ai_models_default_media",
        "ai_models",
        ["media_type"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    op.create_table(
        "text_model_prices",
        sa.Column(
            "model_id",
            sa.String(length=48),
            sa.ForeignKey("ai_models.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "input_price_per_million", sa.Numeric(precision=20, scale=6), server_default="0", nullable=False
        ),
        sa.Column(
            "cached_input_price_per_million",
            sa.Numeric(precision=20, scale=6),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "output_price_per_million", sa.Numeric(precision=20, scale=6), server_default="0", nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("input_price_per_million >= 0", name="ck_text_model_prices_input_nonnegative"),
        sa.CheckConstraint(
            "cached_input_price_per_million >= 0", name="ck_text_model_prices_cached_nonnegative"
        ),
        sa.CheckConstraint("output_price_per_million >= 0", name="ck_text_model_prices_output_nonnegative"),
    )

    op.create_table(
        "image_model_prices",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "model_id",
            sa.String(length=48),
            sa.ForeignKey("ai_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tier", sa.String(length=8), nullable=False),
        sa.Column("credit_price", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("tier IN ('web', '1k', '2k', '4k')", name="ck_image_model_prices_tier_allowed"),
        sa.CheckConstraint("credit_price >= 0", name="ck_image_model_prices_price_nonnegative"),
        sa.UniqueConstraint("model_id", "tier", name="uq_image_model_prices_model_tier"),
    )
    op.create_index("ix_image_model_prices_model_id", "image_model_prices", ["model_id"])

    op.create_table(
        "video_model_prices",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "model_id",
            sa.String(length=48),
            sa.ForeignKey("ai_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule_key", sa.String(length=64), server_default="default", nullable=False),
        sa.Column("unit", sa.String(length=16), server_default="second", nullable=False),
        sa.Column("credit_price", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("unit IN ('second', 'call')", name="ck_video_model_prices_unit_allowed"),
        sa.CheckConstraint("credit_price >= 0", name="ck_video_model_prices_price_nonnegative"),
        sa.UniqueConstraint("model_id", "rule_key", name="uq_video_model_prices_model_rule"),
    )
    op.create_index("ix_video_model_prices_model_id", "video_model_prices", ["model_id"])

    op.create_table(
        "credit_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("business_type", sa.String(length=8), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", sa.String(length=48), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("consumed", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="frozen", nullable=False),
        sa.Column("rate_snapshot", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "business_type IN ('image', 'video')", name="ck_credit_reservations_business_type_allowed"
        ),
        sa.CheckConstraint(
            "status IN ('frozen', 'settled', 'released')", name="ck_credit_reservations_status_allowed"
        ),
        sa.CheckConstraint("amount >= 0", name="ck_credit_reservations_amount_nonnegative"),
        sa.CheckConstraint(
            "(status = 'frozen' AND consumed IS NULL) OR "
            "(status = 'settled' AND consumed IS NOT NULL AND consumed >= 0) OR "
            "(status = 'released' AND consumed IS NOT NULL AND consumed = 0)",
            name="ck_credit_reservations_consumed_valid",
        ),
        sa.UniqueConstraint("business_type", "business_id", name="uq_credit_reservations_business"),
    )
    op.create_index(
        "ix_credit_reservations_user_created", "credit_reservations", ["user_id", "created_at", "id"]
    )

    op.create_table(
        "credit_ledgers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("operator_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "reservation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("credit_reservations.id"),
            nullable=True,
        ),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("balance_change", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("frozen_change", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("balance_before", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("balance_after", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("frozen_before", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("frozen_after", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("token_usage", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "operation IN ('grant', 'freeze', 'settle', 'release', 'llm_consume', 'adjust')",
            name="ck_credit_ledgers_operation_allowed",
        ),
        sa.CheckConstraint(
            "frozen_before >= 0 AND frozen_after >= 0", name="ck_credit_ledgers_frozen_nonnegative"
        ),
        sa.CheckConstraint(
            "balance_after = balance_before + balance_change AND "
            "frozen_after = frozen_before + frozen_change",
            name="ck_credit_ledgers_changes_balanced",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_credit_ledgers_idempotency_key"),
    )
    op.create_index("ix_credit_ledgers_user_created", "credit_ledgers", ["user_id", "created_at", "id"])

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("mode", sa.String(length=16), server_default="story", nullable=False),
        sa.Column("source_text", sa.Text(), server_default="", nullable=False),
        sa.Column("settings", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("outline", postgresql.JSONB(), nullable=True),
        sa.Column("script_confirmed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("mode IN ('story', 'upload')", name="ck_projects_mode_allowed"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_projects_status_allowed"),
    )
    op.create_index("ix_projects_user_updated", "projects", ["user_id", "updated_at", "id"])

    op.create_table(
        "episodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("target_seconds", sa.Integer(), server_default="120", nullable=False),
        sa.Column("seconds", sa.Float(), server_default="0", nullable=False),
        sa.Column("hook", sa.Text(), server_default="", nullable=False),
        sa.Column("cliff", sa.Text(), server_default="", nullable=False),
        sa.Column("hook_beat", postgresql.JSONB(), server_default=sa.text("'[1, 1]'::jsonb"), nullable=False),
        sa.Column("scenes", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("script", sa.Text(), server_default="", nullable=False),
        sa.Column("warnings", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("composed_video_key", sa.Text(), nullable=True),
        sa.Column("composed_video_url", sa.Text(), nullable=True),
        sa.Column("composed_duration", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("number >= 1", name="ck_episodes_number_positive"),
        sa.UniqueConstraint("project_id", "number", name="uq_episodes_project_number"),
    )
    op.create_index("ix_episodes_project_id", "episodes", ["project_id"])

    op.create_table(
        "project_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_code", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("voice", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "episode_numbers", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("image_key", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("image_model_id", sa.String(length=48), nullable=True),
        sa.Column("image_tier", sa.String(length=8), nullable=True),
        sa.Column("image_status", sa.String(length=16), server_default="none", nullable=False),
        sa.Column("last_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('character', 'scene', 'prop')", name="ck_project_assets_kind_allowed"),
        sa.CheckConstraint(
            "image_status IN ('none', 'generating', 'ready', 'failed')",
            name="ck_project_assets_image_status_allowed",
        ),
        sa.CheckConstraint(
            "image_tier IS NULL OR image_tier IN ('web', '1k', '2k', '4k')",
            name="ck_project_assets_image_tier_allowed",
        ),
        sa.UniqueConstraint("project_id", "asset_code", name="uq_project_assets_code"),
    )
    op.create_index("ix_project_assets_project_id", "project_assets", ["project_id"])

    op.create_table(
        "storyboard_clips",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "episode_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("episodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("clip_index", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("prompt_customized", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("references", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("beats", postgresql.JSONB(), nullable=True),
        sa.Column("blocking", sa.Text(), nullable=True),
        sa.Column("cuts", postgresql.JSONB(), nullable=True),
        sa.Column("preview_key", sa.Text(), nullable=True),
        sa.Column("preview_url", sa.Text(), nullable=True),
        sa.Column("video_key", sa.Text(), nullable=True),
        sa.Column("video_url", sa.Text(), nullable=True),
        sa.Column("video_model_id", sa.String(length=48), nullable=True),
        sa.Column("video_status", sa.String(length=16), server_default="none", nullable=False),
        sa.Column("last_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("clip_index >= 1", name="ck_storyboard_clips_clip_index_positive"),
        sa.CheckConstraint("duration_seconds >= 1", name="ck_storyboard_clips_duration_positive"),
        sa.CheckConstraint(
            "video_status IN ('none', 'generating', 'ready', 'failed')",
            name="ck_storyboard_clips_video_status_allowed",
        ),
        sa.UniqueConstraint("episode_id", "clip_index", name="uq_storyboard_clips_episode_index"),
    )
    op.create_index("ix_storyboard_clips_project_id", "storyboard_clips", ["project_id"])
    op.create_index("ix_storyboard_clips_episode_id", "storyboard_clips", ["episode_id"])

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="queued", nullable=False),
        sa.Column("step_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("step_total", sa.Integer(), server_default="1", nullable=False),
        sa.Column("step_label", sa.String(length=200), server_default="", nullable=False),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("input_payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("provider_task_id", sa.String(length=512), nullable=True),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatch_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("usage_summary", postgresql.JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "job_type IN ('script_generate', 'script_regenerate', 'episode_rewrite', "
            "'episode_append', 'assets_extract', 'asset_image', 'storyboard_generate', "
            "'clip_video', 'episode_compose')",
            name="ck_jobs_job_type_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'polling', 'succeeded', 'failed', 'review')",
            name="ck_jobs_status_allowed",
        ),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_jobs_progress_range"),
        sa.UniqueConstraint("idempotency_key", name="uq_jobs_idempotency_key"),
    )
    op.create_index("ix_jobs_user_created", "jobs", ["user_id", "created_at", "id"])
    op.create_index("ix_jobs_project_status", "jobs", ["project_id", "status"])
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"])
    op.create_index(
        "ix_jobs_dispatch_due",
        "jobs",
        ["dispatch_after", "next_attempt_at"],
        postgresql_where=sa.text("status IN ('queued', 'polling')"),
    )


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("storyboard_clips")
    op.drop_table("project_assets")
    op.drop_table("episodes")
    op.drop_table("projects")
    op.drop_table("credit_ledgers")
    op.drop_table("credit_reservations")
    op.drop_table("video_model_prices")
    op.drop_table("image_model_prices")
    op.drop_table("text_model_prices")
    op.drop_table("ai_models")
    op.drop_table("ai_providers")
    op.drop_table("system_settings")
    op.drop_table("users")
