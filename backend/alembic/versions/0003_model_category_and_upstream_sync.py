"""Add model category, upstream_available tracking, and ai_model_sync_logs table."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_model_cat_sync"
down_revision: str | Sequence[str] | None = "0002_add_operator_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_models",
        sa.Column("category", sa.String(length=48), nullable=False, server_default=""),
    )
    op.add_column(
        "ai_models",
        sa.Column("upstream_available", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "ai_models",
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "ai_model_sync_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("provider_key", sa.String(length=32), nullable=False),
        sa.Column("model_id", sa.String(length=48), nullable=False),
        sa.Column("upstream_model_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "event_type IN ('offline', 'restored')",
            name=op.f("ck_ai_model_sync_logs_sync_event_type_allowed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_model_sync_logs")),
    )
    op.create_index(
        op.f("ix_ai_model_sync_logs_provider_key"),
        "ai_model_sync_logs",
        ["provider_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_model_sync_logs_model_id"),
        "ai_model_sync_logs",
        ["model_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_model_sync_logs_created_at",
        "ai_model_sync_logs",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_model_sync_logs_created_at", table_name="ai_model_sync_logs")
    op.drop_index(op.f("ix_ai_model_sync_logs_model_id"), table_name="ai_model_sync_logs")
    op.drop_index(op.f("ix_ai_model_sync_logs_provider_key"), table_name="ai_model_sync_logs")
    op.drop_table("ai_model_sync_logs")
    op.drop_column("ai_models", "last_synced_at")
    op.drop_column("ai_models", "upstream_available")
    op.drop_column("ai_models", "category")
