"""Add parent_asset_id and variant_label to project_assets for unified asset state variants."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_asset_variants"
down_revision: str | Sequence[str] | None = "0005_studio_media_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_assets",
        sa.Column("parent_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "project_assets",
        sa.Column("variant_label", sa.String(length=48), nullable=False, server_default=""),
    )
    op.create_foreign_key(
        op.f("fk_project_assets_parent_asset_id_project_assets"),
        "project_assets",
        "project_assets",
        ["parent_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "parent_not_self",
        "project_assets",
        "parent_asset_id IS NULL OR parent_asset_id <> id",
    )
    op.create_index(
        "ix_project_assets_parent_id",
        "project_assets",
        ["parent_asset_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_project_assets_parent_id", table_name="project_assets")
    op.drop_constraint(
        op.f("ck_project_assets_parent_not_self"),
        "project_assets",
        type_="check",
    )
    op.drop_constraint(
        op.f("fk_project_assets_parent_asset_id_project_assets"),
        "project_assets",
        type_="foreignkey",
    )
    op.drop_column("project_assets", "variant_label")
    op.drop_column("project_assets", "parent_asset_id")
