import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.canvas.service import patch_canvas_node_error
from app.modules.jobs.models import Job
from app.modules.jobs.service import publish_job_event
from app.modules.studio.models import ProjectAsset, StoryboardClip

logger = structlog.get_logger(__name__)

_MEDIA_JOB_TYPES = {"asset_image", "clip_video", "canvas_image", "canvas_video"}
_AUTO_RECOVER_LLM_JOB_TYPES = {
    "script_generate",
    "script_regenerate",
    "assets_extract",
    "storyboard_generate",
}
_LLM_JOB_TYPES = {
    "script_generate",
    "script_regenerate",
    "episode_rewrite",
    "episode_append",
    "assets_extract",
    "storyboard_generate",
    "canvas_text",
}


async def _default_dispatch(job_type: str, job_id: str) -> None:
    from app.workers.ai_tasks import (
        execute_asset_image_job,
        execute_clip_video_job,
        execute_llm_job,
    )
    from app.workers.media_tasks import execute_episode_compose_job

    if job_type in ("asset_image", "canvas_image"):
        await execute_asset_image_job.kiq(job_id)
    elif job_type in ("clip_video", "canvas_video"):
        await execute_clip_video_job.kiq(job_id)
    elif job_type == "episode_compose":
        await execute_episode_compose_job.kiq(job_id)
    elif job_type in _LLM_JOB_TYPES:
        await execute_llm_job.kiq(job_id)


async def sweep_stale_jobs_once(
    *,
    sessions: async_sessionmaker[AsyncSession],
    redis: Any,
    settings: Any,
    dispatcher: Callable[[str, str], Awaitable[None]] | None = None,
    now: datetime | None = None,
    queued_stale_seconds: int = 180,
) -> dict[str, int]:
    """
    轻量巡检恢复器（运行于 ai_broker 后台协程）：
    1. 租约过期的媒体任务：
       - 若已拿到 provider_task_id -> 重置租约并重新投递，直接续查供应商进度（绝不重复建单/扣费）；
       - 若未拿到 provider_task_id -> 无法判断是否已扣上游费用，安全转 review 保留冻结待核对。
    2. 租约过期的 LLM / 合成任务 -> 标记 failed 避免前端永久挂死（不擅自重跑消耗额外 token）。
    3. 长时间滞留 queued（如 Redis 重启丢队列）-> 补投递至对应队列并延后下次重试时间防刷屏。
    """
    lock_key = f"{settings.redis_key_prefix}sweeper:lock"
    acquired = await redis.set(lock_key, "1", nx=True, ex=12)
    if not acquired:
        return {"skipped": 1, "resumed": 0, "requeued": 0, "reviewed": 0, "failed": 0}

    dispatch = dispatcher or _default_dispatch
    current = now or datetime.now(UTC)
    counts = {"skipped": 0, "resumed": 0, "requeued": 0, "reviewed": 0, "failed": 0}
    to_dispatch: list[tuple[str, str]] = []
    to_publish: list[Job] = []

    async with sessions() as session:
        expired_jobs = list(
            await session.scalars(
                select(Job)
                .where(
                    Job.status.in_(("running", "polling")),
                    Job.lease_until.is_not(None),
                    Job.lease_until < current,
                )
                .limit(50)
            )
        )

        for job in expired_jobs:
            job.lease_token = None
            job.lease_until = None
            if job.job_type in _MEDIA_JOB_TYPES and (job.provider_task_id or "").strip():
                job.status = "queued"
                job.step_label = "后台进程已恢复，正在续查供应商进度..."
                job.next_attempt_at = current + timedelta(seconds=queued_stale_seconds)
                to_dispatch.append((job.job_type, str(job.id)))
                to_publish.append(job)
                counts["resumed"] += 1
            elif job.job_type in _MEDIA_JOB_TYPES:
                job.status = "review"
                job.error_code = "worker_lease_expired"
                job.error_message = (
                    "后台执行超时或进程中断，未获取到供应商任务号，已转人工核对（冻结积分暂保留）"
                )
                job.finished_at = current
                if (
                    job.job_type == "asset_image"
                    and job.target_id
                    and (job.input_payload or {}).get("action") != "clip_storyboard_grid"
                ):
                    asset = await session.scalar(
                        select(ProjectAsset).where(ProjectAsset.id == UUID(job.target_id))
                    )
                    if asset is not None:
                        asset.image_status = "ready" if asset.image_url else "failed"
                elif job.job_type == "clip_video" and job.target_id:
                    clip = await session.scalar(
                        select(StoryboardClip).where(StoryboardClip.id == UUID(job.target_id))
                    )
                    if clip is not None:
                        clip.video_status = "ready" if clip.video_url else "failed"
                elif job.job_type in ("canvas_image", "canvas_video") and job.canvas_id and job.target_id:
                    await patch_canvas_node_error(
                        session,
                        canvas_id=job.canvas_id,
                        node_id=job.target_id,
                        error_message=job.error_message,
                        job_id=job.id,
                    )
                to_publish.append(job)
                counts["reviewed"] += 1
            elif job.job_type in _AUTO_RECOVER_LLM_JOB_TYPES:
                payload = dict(job.input_payload or {})
                recoveries = int(payload.get("crashRecoveries") or 0)
                max_recoveries = max(
                    0, int(getattr(settings, "script_crash_max_recoveries", 2) or 0)
                )
                if recoveries < max_recoveries:
                    next_recovery = recoveries + 1
                    job.input_payload = {**payload, "crashRecoveries": next_recovery}
                    job.status = "queued"
                    job.step_label = (
                        "检测到后台节点切换，正在从断点自动续写"
                        f"（第 {next_recovery}/{max_recoveries} 次恢复）"
                    )
                    job.dispatch_after = current
                    job.next_attempt_at = current + timedelta(seconds=queued_stale_seconds)
                    to_dispatch.append((job.job_type, str(job.id)))
                    to_publish.append(job)
                    counts["resumed"] += 1
                else:
                    job.status = "failed"
                    job.error_code = "worker_lease_expired"
                    job.error_message = (
                        "后台多次意外中断，已暂停自动恢复，请点击继续生成剩余分集"
                        if job.job_type in ("script_generate", "script_regenerate")
                        else "后台多次意外中断，已暂停自动恢复，请重新发起任务"
                    )
                    job.finished_at = current
                    to_publish.append(job)
                    counts["failed"] += 1
            else:
                job.status = "failed"
                job.error_code = "worker_lease_expired"
                job.error_message = "后台执行超时或进程意外中断，请重新发起"
                job.finished_at = current
                if job.job_type == "canvas_text" and job.canvas_id and job.target_id:
                    await patch_canvas_node_error(
                        session,
                        canvas_id=job.canvas_id,
                        node_id=job.target_id,
                        error_message=job.error_message,
                        job_id=job.id,
                    )
                to_publish.append(job)
                counts["failed"] += 1

        stale_cutoff = current - timedelta(seconds=queued_stale_seconds)
        queued_jobs = list(
            await session.scalars(
                select(Job)
                .where(
                    Job.status == "queued",
                    or_(Job.next_attempt_at.is_(None), Job.next_attempt_at <= current),
                    or_(Job.dispatch_after.is_(None), Job.dispatch_after <= current),
                    or_(
                        Job.created_at < stale_cutoff,
                        and_(
                            Job.dispatch_after.is_not(None),
                            Job.dispatch_after > Job.created_at,
                        ),
                    ),
                )
                .limit(50)
            )
        )
        for job in queued_jobs:
            job.next_attempt_at = current + timedelta(seconds=queued_stale_seconds)
            to_dispatch.append((job.job_type, str(job.id)))
            counts["requeued"] += 1

        await session.commit()

    for job in to_publish:
        await publish_job_event(redis, settings, job)

    for job_type, job_id in to_dispatch:
        try:
            await dispatch(job_type, job_id)
        except Exception:
            logger.exception("sweeper_dispatch_failed", job_type=job_type, job_id=job_id)

    if any(counts[k] > 0 for k in ("resumed", "requeued", "reviewed", "failed")):
        logger.info("sweeper_cycle_completed", **counts)
    return counts


async def sweeper_loop(
    *,
    sessions: async_sessionmaker[AsyncSession],
    redis: Any,
    settings: Any,
    interval_seconds: float = 15.0,
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await sweep_stale_jobs_once(sessions=sessions, redis=redis, settings=settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("sweeper_cycle_error")
