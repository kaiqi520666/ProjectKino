"""Add image_history to project_assets and video_history to storyboard_clips with backfill."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_studio_media_history"
down_revision: str | Sequence[str] | None = "0004_canvas_and_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MAX_HISTORY = 20


def _iso_utc(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _append_dedup(items: list[dict[str, Any]], entry: dict[str, Any]) -> list[dict[str, Any]]:
    url = str(entry.get("url") or "").strip()
    if not url:
        return items
    job_id = entry.get("jobId")
    filtered = [
        item
        for item in items
        if item.get("url") != url and (not job_id or item.get("jobId") != job_id)
    ]
    filtered.append(entry)
    return filtered[-_MAX_HISTORY:]


def _backfill_histories() -> None:
    bind = op.get_bind()

    asset_jobs = bind.execute(
        sa.text(
            """
            SELECT id, target_id, input_payload, result_payload, created_at, finished_at
            FROM jobs
            WHERE job_type = 'asset_image'
              AND status = 'succeeded'
              AND target_id IS NOT NULL
            ORDER BY created_at ASC, id ASC
            """
        )
    ).mappings().all()

    asset_history_map: dict[str, list[dict[str, Any]]] = {}
    for row in asset_jobs:
        target_id = str(row["target_id"])
        result_payload = row["result_payload"] or {}
        input_payload = row["input_payload"] or {}
        url = str(result_payload.get("imageUrl") or "").strip()
        if not url:
            continue
        key = str(result_payload.get("imageKey") or "").strip() or None
        model_id = str(result_payload.get("modelId") or input_payload.get("modelId") or "").strip() or None
        tier = str(result_payload.get("tier") or input_payload.get("tier") or "").strip() or None
        ratio = str(result_payload.get("ratio") or input_payload.get("ratio") or "").strip() or None
        job_id = str(row["id"])
        entry: dict[str, Any] = {
            "id": job_id,
            "url": url,
            "key": key,
            "source": "ai",
            "jobId": job_id,
            "modelId": model_id,
            "tier": tier,
            "resolution": None,
            "ratio": ratio,
            "duration": None,
            "createdAt": _iso_utc(row["finished_at"] or row["created_at"]),
        }
        asset_history_map[target_id] = _append_dedup(asset_history_map.get(target_id, []), entry)

    assets = bind.execute(
        sa.text(
            """
            SELECT id, image_url, image_key, image_model_id, image_tier, updated_at, created_at
            FROM project_assets
            """
        )
    ).mappings().all()

    for asset in assets:
        aid = str(asset["id"])
        history = list(asset_history_map.get(aid, []))
        current_url = str(asset["image_url"] or "").strip()
        if current_url and not any(item.get("url") == current_url for item in history):
            history = _append_dedup(
                history,
                {
                    "id": str(uuid4()),
                    "url": current_url,
                    "key": str(asset["image_key"] or "").strip() or None,
                    "source": "upload" if not asset["image_model_id"] else "ai",
                    "jobId": None,
                    "modelId": asset["image_model_id"],
                    "tier": asset["image_tier"],
                    "resolution": None,
                    "ratio": None,
                    "duration": None,
                    "createdAt": _iso_utc(asset["updated_at"] or asset["created_at"]),
                },
            )
        if history:
            bind.execute(
                sa.text(
                    "UPDATE project_assets SET image_history = CAST(:history AS jsonb) WHERE id = :id"
                ),
                {"id": asset["id"], "history": json.dumps(history, ensure_ascii=False)},
            )

    clip_jobs = bind.execute(
        sa.text(
            """
            SELECT id, target_id, input_payload, result_payload, created_at, finished_at
            FROM jobs
            WHERE job_type = 'clip_video'
              AND status = 'succeeded'
              AND target_id IS NOT NULL
            ORDER BY created_at ASC, id ASC
            """
        )
    ).mappings().all()

    clip_history_map: dict[str, list[dict[str, Any]]] = {}
    for row in clip_jobs:
        target_id = str(row["target_id"])
        result_payload = row["result_payload"] or {}
        input_payload = row["input_payload"] or {}
        url = str(result_payload.get("videoUrl") or "").strip()
        if not url:
            continue
        key = str(result_payload.get("videoKey") or "").strip() or None
        model_id = str(result_payload.get("modelId") or input_payload.get("modelId") or "").strip() or None
        resolution = (
            str(result_payload.get("resolution") or input_payload.get("resolution") or "").strip() or None
        )
        ratio = str(result_payload.get("ratio") or input_payload.get("ratio") or "").strip() or None
        raw_duration = result_payload.get("duration") or input_payload.get("durationSeconds")
        duration = float(raw_duration) if isinstance(raw_duration, (int, float)) else None
        job_id = str(row["id"])
        entry = {
            "id": job_id,
            "url": url,
            "key": key,
            "source": "ai",
            "jobId": job_id,
            "modelId": model_id,
            "tier": None,
            "resolution": resolution,
            "ratio": ratio,
            "duration": duration,
            "createdAt": _iso_utc(row["finished_at"] or row["created_at"]),
        }
        clip_history_map[target_id] = _append_dedup(clip_history_map.get(target_id, []), entry)

    clips = bind.execute(
        sa.text(
            """
            SELECT id, video_url, video_key, video_model_id, duration_seconds, updated_at, created_at
            FROM storyboard_clips
            """
        )
    ).mappings().all()

    for clip in clips:
        cid = str(clip["id"])
        history = list(clip_history_map.get(cid, []))
        current_url = str(clip["video_url"] or "").strip()
        if current_url and not any(item.get("url") == current_url for item in history):
            history = _append_dedup(
                history,
                {
                    "id": str(uuid4()),
                    "url": current_url,
                    "key": str(clip["video_key"] or "").strip() or None,
                    "source": "ai",
                    "jobId": None,
                    "modelId": clip["video_model_id"],
                    "tier": None,
                    "resolution": None,
                    "ratio": None,
                    "duration": float(clip["duration_seconds"]) if clip["duration_seconds"] else None,
                    "createdAt": _iso_utc(clip["updated_at"] or clip["created_at"]),
                },
            )
        if history:
            bind.execute(
                sa.text(
                    "UPDATE storyboard_clips SET video_history = CAST(:history AS jsonb) WHERE id = :id"
                ),
                {"id": clip["id"], "history": json.dumps(history, ensure_ascii=False)},
            )


def upgrade() -> None:
    op.add_column(
        "project_assets",
        sa.Column(
            "image_history",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "storyboard_clips",
        sa.Column(
            "video_history",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    _backfill_histories()


def downgrade() -> None:
    op.drop_column("storyboard_clips", "video_history")
    op.drop_column("project_assets", "image_history")
