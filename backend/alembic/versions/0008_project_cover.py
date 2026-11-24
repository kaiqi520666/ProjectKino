"""Add cover_key and cover_url columns on projects."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_project_cover"
down_revision: str | Sequence[str] | None = "0007_video_default_30s"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("cover_key", sa.String(length=512), nullable=True))
    op.add_column("projects", sa.Column("cover_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "cover_url")
    op.drop_column("projects", "cover_key")
