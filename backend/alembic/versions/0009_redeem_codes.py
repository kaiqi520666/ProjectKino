"""Add redeem_codes, redeem_code_uses tables and allow redeem ledger operation."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009_redeem_codes"
down_revision: str | Sequence[str] | None = "0008_project_cover"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_credit_ledgers_operation_allowed", "credit_ledgers", type_="check")
    op.create_check_constraint(
        "ck_credit_ledgers_operation_allowed",
        "credit_ledgers",
        "operation IN ('grant', 'freeze', 'settle', 'release', 'llm_consume', 'adjust', 'redeem')",
    )

    op.create_table(
        "redeem_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("code_normalized", sa.String(length=64), nullable=False),
        sa.Column("batch_name", sa.String(length=120), server_default="", nullable=False),
        sa.Column("credits", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("max_uses", sa.Integer(), server_default="1", nullable=False),
        sa.Column("used_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
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
        sa.UniqueConstraint("code_normalized", name="uq_redeem_codes_normalized"),
        sa.CheckConstraint("credits > 0", name="ck_redeem_codes_credits_positive"),
        sa.CheckConstraint("max_uses >= 1", name="ck_redeem_codes_max_uses_positive"),
        sa.CheckConstraint(
            "used_count >= 0 AND used_count <= max_uses",
            name="ck_redeem_codes_used_count_bounds",
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_redeem_codes_status_allowed"),
    )
    op.create_index("ix_redeem_codes_batch_created", "redeem_codes", ["batch_name", "created_at"])
    op.create_index("ix_redeem_codes_status_created", "redeem_codes", ["status", "created_at"])

    op.create_table(
        "redeem_code_uses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "code_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("redeem_codes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("credits", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column(
            "ledger_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("credit_ledgers.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("code_id", "user_id", name="uq_redeem_code_uses_code_user"),
    )
    op.create_index("ix_redeem_code_uses_code_created", "redeem_code_uses", ["code_id", "created_at"])
    op.create_index("ix_redeem_code_uses_user_created", "redeem_code_uses", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_redeem_code_uses_user_created", table_name="redeem_code_uses")
    op.drop_index("ix_redeem_code_uses_code_created", table_name="redeem_code_uses")
    op.drop_table("redeem_code_uses")

    op.drop_index("ix_redeem_codes_status_created", table_name="redeem_codes")
    op.drop_index("ix_redeem_codes_batch_created", table_name="redeem_codes")
    op.drop_table("redeem_codes")

    op.drop_constraint("ck_credit_ledgers_operation_allowed", "credit_ledgers", type_="check")
    op.create_check_constraint(
        "ck_credit_ledgers_operation_allowed",
        "credit_ledgers",
        "operation IN ('grant', 'freeze', 'settle', 'release', 'llm_consume', 'adjust')",
    )
