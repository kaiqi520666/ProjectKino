import asyncio
import json
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from redis.asyncio import Redis
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.jobs.models import Job
from app.modules.jobs.schemas import JobOut

logger = structlog.get_logger(__name__)

TERMINAL_STATUSES = {"succeeded", "failed", "review"}


def job_channel(settings: Settings, job_id: UUID) -> str:
    return f"{settings.redis_key_prefix}job_events:{job_id}"


def serialize_job(job: Job) -> dict[str, Any]:
    return JobOut.model_validate(job).model_dump(by_alias=True, mode="json")


async def publish_job_event(redis: Redis, settings: Settings, job: Job) -> None:
    try:
        payload = json.dumps(serialize_job(job), ensure_ascii=False)
        await redis.publish(job_channel(settings, job.id), payload)
    except Exception:
        logger.warning("job_event_publish_failed", job_id=str(job.id))


async def create_job(
    session: AsyncSession,
    *,
    user_id: int,
    project_id: UUID | None,
    job_type: str,
    input_payload: dict[str, Any],
    step_total: int = 1,
    step_label: str = "任务已排队，等待执行",
    target_id: str | None = None,
    idempotency_key: str | None = None,
    canvas_id: UUID | None = None,
) -> Job:
    if idempotency_key:
        existing = await session.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
        if existing is not None:
            return existing

    now = datetime.now(UTC)
    job = Job(
        user_id=user_id,
        project_id=project_id,
        canvas_id=canvas_id,
        job_type=job_type,
        target_id=target_id,
        status="queued",
        step_index=0,
        step_total=max(1, step_total),
        step_label=step_label,
        progress=0,
        input_payload=input_payload,
        idempotency_key=idempotency_key,
        next_attempt_at=now,
        dispatch_after=now,
    )
    session.add(job)
    await session.flush()
    return job


async def get_user_job(session: AsyncSession, *, job_id: UUID, user_id: int) -> Job:
    job = await session.scalar(select(Job).where(Job.id == job_id, Job.user_id == user_id))
    if job is None:
        raise AppError(404, "job_not_found", "任务不存在")
    return job


async def list_project_jobs(
    session: AsyncSession, *, project_id: UUID, user_id: int, limit: int = 20
) -> list[Job]:
    return list(
        await session.scalars(
            select(Job)
            .where(Job.project_id == project_id, Job.user_id == user_id)
            .order_by(desc(Job.created_at), desc(Job.id))
            .limit(max(1, min(limit, 50)))
        )
    )


async def claim_job_lease(
    sessions: async_sessionmaker[AsyncSession],
    job_id: UUID,
    *,
    lease_seconds: int = 300,
) -> tuple[Job, str] | None:
    token = secrets.token_hex(16)
    now = datetime.now(UTC)
    async with sessions() as session:
        job = await session.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if job is None or job.status in TERMINAL_STATUSES:
            return None
        if job.status in ("running", "polling") and job.lease_until and job.lease_until > now:
            return None
        if job.status == "queued" and job.dispatch_after and job.dispatch_after > now:
            return None
        job.status = "running"
        job.lease_token = token
        job.lease_until = now + timedelta(seconds=lease_seconds)
        if job.started_at is None:
            job.started_at = now
        await session.commit()
        await session.refresh(job)
        return job, token


async def heartbeat_job_lease(
    sessions: async_sessionmaker[AsyncSession],
    job_id: UUID,
    token: str,
    *,
    interval_seconds: int = 30,
    lease_seconds: int = 300,
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        now = datetime.now(UTC)
        try:
            async with sessions() as session:
                await session.execute(
                    update(Job)
                    .where(Job.id == job_id, Job.lease_token == token)
                    .values(lease_until=now + timedelta(seconds=lease_seconds))
                )
                await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("job_lease_heartbeat_failed", job_id=str(job_id), error=str(exc))


async def update_job_progress(
    sessions: async_sessionmaker[AsyncSession],
    redis: Redis,
    settings: Settings,
    *,
    job_id: UUID,
    step_index: int,
    step_total: int,
    step_label: str,
    progress: int,
) -> None:
    async with sessions() as session:
        job = await session.scalar(select(Job).where(Job.id == job_id))
        if job is None or job.status in TERMINAL_STATUSES:
            return
        job.step_index = step_index
        job.step_total = max(1, step_total)
        job.step_label = step_label[:200]
        job.progress = max(0, min(100, progress))
        await session.commit()
        await session.refresh(job)
    await publish_job_event(redis, settings, job)


async def stream_job_events(
    *,
    sessions: async_sessionmaker[AsyncSession],
    redis: Redis,
    settings: Settings,
    job_id: UUID,
    user_id: int,
) -> AsyncIterator[str]:
    async with sessions() as session:
        job = await get_user_job(session, job_id=job_id, user_id=user_id)
        initial = serialize_job(job)
        terminal = job.status in TERMINAL_STATUSES

    yield f"event: progress\ndata: {json.dumps(initial, ensure_ascii=False)}\n\n"
    if terminal:
        return

    pubsub = redis.pubsub()
    channel = job_channel(settings, job_id)
    await pubsub.subscribe(channel)
    try:
        while True:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0),
                    timeout=16.0,
                )
            except TimeoutError:
                message = None

            if message and message.get("type") == "message":
                raw = message["data"]
                text_data = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                yield f"event: progress\ndata: {text_data}\n\n"
                try:
                    parsed = json.loads(text_data)
                    if parsed.get("status") in TERMINAL_STATUSES:
                        return
                except ValueError:
                    pass
            else:
                # 定时心跳同时兜底同步数据库状态，防止遗漏终态事件。
                async with sessions() as session:
                    current = await session.scalar(select(Job).where(Job.id == job_id))
                    if current is None:
                        return
                    if current.status in TERMINAL_STATUSES:
                        payload = json.dumps(serialize_job(current), ensure_ascii=False)
                        yield f"event: progress\ndata: {payload}\n\n"
                        return
                yield ": keepalive\n\n"
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
