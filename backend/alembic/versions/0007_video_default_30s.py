"""Add is_default_long column on ai_models for 30s video default model."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_video_default_30s"
down_revision: str | Sequence[str] | None = "0006_asset_variants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_models",
        sa.Column("is_default_long", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_check_constraint(
        "default_long_video_enabled",
        "ai_models",
        "NOT is_default_long OR (enabled AND media_type = 'video')",
    )
    op.create_index(
        "uq_ai_models_default_video_long",
        "ai_models",
        ["media_type"],
        unique=True,
        postgresql_where=sa.text("is_default_long"),
    )
    op.execute(
        sa.text(
            """
            UPDATE ai_models
            SET is_default_long = true
            WHERE id = (
                SELECT m.id
                FROM ai_models m
                JOIN ai_providers p ON p.id = m.provider_id
                WHERE m.media_type = 'video'
                  AND m.enabled = true
                  AND m.upstream_available = true
                  AND p.enabled = true
                  AND (m.capabilities->>'maxDuration') ~ '^[0-9]+$'
                  AND (m.capabilities->>'maxDuration')::int >= 30
                ORDER BY m.sort ASC, m.id ASC
                LIMIT 1
            )
            AND NOT EXISTS (
                SELECT 1 FROM ai_models WHERE is_default_long = true
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_index("uq_ai_models_default_video_long", table_name="ai_models")
    op.drop_constraint(
        op.f("ck_ai_models_default_long_video_enabled"),
        "ai_models",
        type_="check",
    )
    op.drop_column("ai_models", "is_default_long")
