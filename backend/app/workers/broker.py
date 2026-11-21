import asyncio
from dataclasses import dataclass

import httpx
import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from taskiq import TaskiqEvents, TaskiqState
from taskiq_redis import ListQueueBroker

from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.session import create_engine, dispose_engine
from app.modules.catalog.upstream_sync import upstream_sync_loop
from app.workers.sweeper import sweeper_loop

settings = Settings()

ai_broker = ListQueueBroker(
    url=settings.redis_url.get_secret_value(),
    queue_name=f"{settings.redis_key_prefix}queue:ai_io",
    socket_timeout=None,
    socket_connect_timeout=5,
    socket_keepalive=True,
)

media_broker = ListQueueBroker(
    url=settings.redis_url.get_secret_value(),
    queue_name=f"{settings.redis_key_prefix}queue:media_cpu",
    socket_timeout=None,
    socket_connect_timeout=5,
    socket_keepalive=True,
)


@dataclass
class WorkerRuntime:
    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    redis: Redis
    http: httpx.AsyncClient


async def _init_runtime(state: TaskiqState) -> None:
    cfg = Settings()
    configure_logging(cfg.log_level)
    engine = create_engine(cfg)
    redis = Redis.from_url(
        cfg.redis_url.get_secret_value(),
        decode_responses=True,
        socket_connect_timeout=cfg.dependency_timeout_seconds,
        socket_timeout=None,
        socket_keepalive=True,
    )
    http = httpx.AsyncClient(timeout=30.0, follow_redirects=False)
    state.runtime = WorkerRuntime(
        settings=cfg,
        engine=engine,
        sessions=async_sessionmaker(engine, expire_on_commit=False),
        redis=redis,
        http=http,
    )
    structlog.get_logger(__name__).info("worker_started", environment=cfg.environment)


async def _close_runtime(state: TaskiqState) -> None:
    runtime: WorkerRuntime | None = getattr(state, "runtime", None)
    if runtime is None:
        return
    await runtime.http.aclose()
    await runtime.redis.aclose()
    await dispose_engine(runtime.engine)
    structlog.get_logger(__name__).info("worker_stopped")


async def _init_ai_runtime(state: TaskiqState) -> None:
    await _init_runtime(state)
    runtime: WorkerRuntime = state.runtime
    state.sweeper_task = asyncio.create_task(
        sweeper_loop(sessions=runtime.sessions, redis=runtime.redis, settings=runtime.settings)
    )
    state.upstream_sync_task = asyncio.create_task(
        upstream_sync_loop(
            sessions=runtime.sessions,
            redis=runtime.redis,
            settings=runtime.settings,
            http_client=runtime.http,
            provider_key="cc",
            interval_seconds=300.0,
        )
    )


async def _close_ai_runtime(state: TaskiqState) -> None:
    for attr in ("sweeper_task", "upstream_sync_task"):
        task: asyncio.Task | None = getattr(state, attr, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    await _close_runtime(state)


ai_broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, _init_ai_runtime)
ai_broker.add_event_handler(TaskiqEvents.WORKER_SHUTDOWN, _close_ai_runtime)
media_broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, _init_runtime)
media_broker.add_event_handler(TaskiqEvents.WORKER_SHUTDOWN, _close_runtime)
