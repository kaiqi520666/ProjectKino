import asyncio
import tempfile
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from taskiq import Context, TaskiqDepends

from app.core.errors import AppError
from app.modules.composer.ffmpeg import compose_episode_videos
from app.modules.jobs.models import Job
from app.modules.jobs.service import (
    claim_job_lease,
    heartbeat_job_lease,
    publish_job_event,
    update_job_progress,
)
from app.modules.storage.media import download_to_file
from app.modules.storage.oss import OssStorage, load_storage
from app.modules.studio.models import Episode, StoryboardClip
from app.workers.broker import WorkerRuntime, media_broker

logger = structlog.get_logger(__name__)


async def run_episode_compose_job_core(
    *,
    sessions: async_sessionmaker[AsyncSession],
    redis: Any,
    settings: Any,
    job_id: UUID,
    storage_loader: Callable[[AsyncSession], Awaitable[OssStorage]] = load_storage,
    file_downloader: Callable[[str, Path], Awaitable[int]] = download_to_file,
    composer: Callable[..., Awaitable[float]] = compose_episode_videos,
) -> None:
    """
    FFmpeg 本集视频免费合成状态机（运行于独立 media_broker）：
    - 0 积分免费，不冻结、不扣费；
    - 从 OSS / 公网拉取全部片段 -> FFmpeg 归一化拼接 -> 回传 OSS -> 写回 episodes.composed_video_*。
    """
    claimed = await claim_job_lease(sessions, job_id)
    if claimed is None:
        return
    job, lease_token = claimed
    await publish_job_event(redis, settings, job)

    heartbeat = asyncio.create_task(heartbeat_job_lease(sessions, job_id, lease_token))

    async def set_progress(step_index: int, label: str, progress: int) -> None:
        await update_job_progress(
            sessions,
            redis,
            settings,
            job_id=job_id,
            step_index=step_index,
            step_total=4,
            step_label=label,
            progress=progress,
        )

    try:
        async with sessions() as session:
            episode_id = UUID(str(job.target_id or (job.input_payload or {}).get("episodeId")))
            episode = await session.scalar(select(Episode).where(Episode.id == episode_id))
            if episode is None:
                raise AppError(404, "episode_not_found", "关联分集不存在")
            clips = list(
                await session.scalars(
                    select(StoryboardClip)
                    .where(StoryboardClip.episode_id == episode.id)
                    .order_by(StoryboardClip.clip_index)
                )
            )
            if not clips:
                raise AppError(400, "clips_required", "本集尚无分镜片段，无法合成")
            missing = [str(c.clip_index) for c in clips if not (c.video_key or c.video_url)]
            if missing:
                raise AppError(
                    400,
                    "clip_videos_incomplete",
                    f"片段 {'、'.join(missing)} 尚未生成视频，请先全部生成后再合成",
                )
            storage = await storage_loader(session)
            clip_sources = [(c.clip_index, c.video_key, c.video_url) for c in clips]
            episode_number = episode.number

        with tempfile.TemporaryDirectory(prefix="framedrama_compose_") as tmp_dir:
            work_dir = Path(tmp_dir)
            clip_paths: list[Path] = []
            total_clips = len(clip_sources)

            for idx, (clip_index, video_key, video_url) in enumerate(clip_sources, 1):
                pct = 10 + int((idx - 1) / max(1, total_clips) * 35)
                await set_progress(1, f"正在拉取片段 {clip_index}（{idx}/{total_clips}）...", pct)
                dest = work_dir / f"clip_{idx:03d}.mp4"
                if video_key:
                    await asyncio.to_thread(storage.download_file, video_key, str(dest))
                elif video_url:
                    await file_downloader(video_url, dest)
                clip_paths.append(dest)

            await set_progress(2, f"正在使用 FFmpeg 合成第 {episode_number} 集（共 {total_clips} 段）...", 55)
            output_path = work_dir / f"episode_{episode_number}_{job.id}.mp4"
            composed_duration = await composer(
                clip_paths,
                output_path,
                ffmpeg_path=getattr(settings, "ffmpeg_path", "ffmpeg"),
                ffprobe_path=getattr(settings, "ffprobe_path", "ffprobe"),
            )

            await set_progress(3, "正在上传合成本集视频至阿里云 OSS...", 85)
            key = storage.make_key(job.user_id, f"episodes/{episode_id}", f"{job.id}.mp4")
            await asyncio.to_thread(storage.put_file, key, str(output_path), "video/mp4")
            public_url = storage.public_url(key)

        async with sessions() as session:
            db_episode = await session.scalar(select(Episode).where(Episode.id == episode_id))
            if db_episode is not None:
                db_episode.composed_video_key = key
                db_episode.composed_video_url = public_url
                db_episode.composed_duration = composed_duration
            db_job = await session.scalar(select(Job).where(Job.id == job_id))
            if db_job is not None:
                db_job.status = "succeeded"
                db_job.progress = 100
                db_job.step_index = 4
                db_job.step_total = 4
                db_job.step_label = "本集视频合成完成"
                db_job.result_payload = {
                    "projectId": str(job.project_id) if job.project_id else None,
                    "episodeId": str(episode_id),
                    "episodeNumber": episode_number,
                    "composedVideoUrl": public_url,
                    "composedVideoKey": key,
                    "composedDuration": composed_duration,
                }
                db_job.finished_at = datetime.now(UTC)
                db_job.lease_token = None
            await session.commit()
            if db_job is not None:
                await session.refresh(db_job)
                await publish_job_event(redis, settings, db_job)

    except Exception as exc:
        code = exc.code if isinstance(exc, AppError) else type(exc).__name__
        message = exc.message if isinstance(exc, AppError) else (str(exc)[:1000] or "本集视频合成失败")
        logger.warning("episode_compose_failed", job_id=str(job_id), code=code, error=message)
        async with sessions() as session:
            db_job = await session.scalar(select(Job).where(Job.id == job_id))
            if db_job is not None:
                db_job.status = "failed"
                db_job.error_code = code
                db_job.error_message = message
                db_job.finished_at = datetime.now(UTC)
                db_job.lease_token = None
            await session.commit()
            if db_job is not None:
                await session.refresh(db_job)
                await publish_job_event(redis, settings, db_job)
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass


@media_broker.task(task_name="framedrama.media.execute_episode_compose_job")
async def execute_episode_compose_job(
    job_id: str,
    context: Context = TaskiqDepends(),
) -> None:
    runtime: WorkerRuntime = context.state.runtime
    await run_episode_compose_job_core(
        sessions=runtime.sessions,
        redis=runtime.redis,
        settings=runtime.settings,
        job_id=UUID(job_id),
    )
