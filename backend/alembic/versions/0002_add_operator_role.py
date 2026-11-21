"""add operator role to users

Revision ID: 0002_add_operator_role
Revises: 0001_v1_initial
Create Date: 2026-11-21 17:58:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_add_operator_role"
down_revision: str | Sequence[str] | None = "0001_v1_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_users_role_allowed", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role_allowed",
        "users",
        "role IN ('user', 'operator', 'admin')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_role_allowed", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role_allowed",
        "users",
        "role IN ('user', 'admin')",
    )
