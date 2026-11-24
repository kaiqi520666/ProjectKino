"""Add art_styles table."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_art_styles"
down_revision: str | Sequence[str] | None = "0010_announcements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "art_styles",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("image_key", sa.String(length=512), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="100", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("code", name="uq_art_styles_code"),
    )
    op.create_index("ix_art_styles_enabled_sort", "art_styles", ["is_enabled", "sort_order", "id"])
    op.create_index(
        "uq_art_styles_single_default",
        "art_styles",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("uq_art_styles_single_default", table_name="art_styles")
    op.drop_index("ix_art_styles_enabled_sort", table_name="art_styles")
    op.drop_table("art_styles")
