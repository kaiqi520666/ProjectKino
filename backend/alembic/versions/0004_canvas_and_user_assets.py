"""Add canvases, user_assets tables, and extend jobs for canvas generation."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_canvas_and_assets"
down_revision: str | Sequence[str] | None = "0003_model_cat_sync"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_JOB_TYPES_SQL = (
    "job_type IN ('script_generate', 'script_regenerate', 'episode_rewrite', "
    "'episode_append', 'assets_extract', 'asset_image', 'storyboard_generate', "
    "'clip_video', 'episode_compose')"
)
_NEW_JOB_TYPES_SQL = (
    "job_type IN ('script_generate', 'script_regenerate', 'episode_rewrite', "
    "'episode_append', 'assets_extract', 'asset_image', 'storyboard_generate', "
    "'clip_video', 'episode_compose', 'canvas_text', 'canvas_image', 'canvas_video')"
)


def upgrade() -> None:
    op.create_table(
        "canvases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("cover_key", sa.String(length=512), nullable=True),
        sa.Column("cover_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("node_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("viewport", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "graph_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{\"nodes\": [], \"edges\": []}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name=op.f("ck_canvases_canvas_status_allowed"),
        ),
        sa.CheckConstraint(
            "schema_version >= 1",
            name=op.f("ck_canvases_canvas_schema_version_positive"),
        ),
        sa.CheckConstraint(
            "version >= 1",
            name=op.f("ck_canvases_canvas_version_positive"),
        ),
        sa.CheckConstraint(
            "node_count >= 0",
            name=op.f("ck_canvases_canvas_node_count_nonnegative"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_canvases_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_canvases")),
    )
    op.create_index(
        "ix_canvases_user_status_updated",
        "canvases",
        ["user_id", "status", "updated_at"],
        unique=False,
    )

    op.create_table(
        "user_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("media_key", sa.String(length=512), nullable=True),
        sa.Column("media_url", sa.Text(), nullable=True),
        sa.Column("media_name", sa.String(length=255), nullable=True),
        sa.Column("source_type", sa.String(length=16), nullable=False, server_default="canvas"),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "kind IN ('text', 'image', 'video', 'audio')",
            name=op.f("ck_user_assets_user_asset_kind_allowed"),
        ),
        sa.CheckConstraint(
            "source_type IN ('canvas', 'studio', 'upload')",
            name=op.f("ck_user_assets_user_asset_source_allowed"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_assets_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_assets")),
    )
    op.create_index(
        "ix_user_assets_user_kind_created",
        "user_assets",
        ["user_id", "kind", "created_at"],
        unique=False,
    )

    op.add_column("jobs", sa.Column("canvas_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_jobs_canvas_id_canvases"),
        "jobs",
        "canvases",
        ["canvas_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_jobs_canvas_id"), "jobs", ["canvas_id"], unique=False)
    op.create_index("ix_jobs_canvas_status", "jobs", ["canvas_id", "status"], unique=False)
    op.drop_constraint("ck_jobs_job_type_allowed", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_job_type_allowed", "jobs", _NEW_JOB_TYPES_SQL)
    op.create_check_constraint(
        "ck_jobs_job_owner_exclusive",
        "jobs",
        "NOT (project_id IS NOT NULL AND canvas_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_jobs_job_owner_exclusive", "jobs", type_="check")
    op.drop_constraint("ck_jobs_job_type_allowed", "jobs", type_="check")
    op.create_check_constraint("ck_jobs_job_type_allowed", "jobs", _OLD_JOB_TYPES_SQL)
    op.drop_index("ix_jobs_canvas_status", table_name="jobs")
    op.drop_index(op.f("ix_jobs_canvas_id"), table_name="jobs")
    op.drop_constraint(op.f("fk_jobs_canvas_id_canvases"), "jobs", type_="foreignkey")
    op.drop_column("jobs", "canvas_id")
    op.drop_index("ix_user_assets_user_kind_created", table_name="user_assets")
    op.drop_table("user_assets")
    op.drop_index("ix_canvases_user_status_updated", table_name="canvases")
    op.drop_table("canvases")
