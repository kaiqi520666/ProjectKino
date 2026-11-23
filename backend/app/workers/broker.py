import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import httpx
import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from taskiq import TaskiqEvents, TaskiqState
from taskiq_redis import ListQueueBroker

from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.session import create_engine, dispose_engine
from app.modules.catalog.upstream_sync import upstream_sync_loop
from app.workers.sweeper import sweeper_loop

settings = Settings()


class ResilientListQueueBroker(ListQueueBroker):
    """
    兜底修复上游 taskiq_redis.ListQueueBroker.listen() 的两个隐患：
    1. 上游只捕获内置 ConnectionError，漏掉 redis.exceptions.ConnectionError（不继承自内置 ConnectionError），
       导致 Windows/Docker 下 TCP 断连（WinError 10054）直接打崩整个 worker 并杀死正在运行的任务；
    2. 上游默认 brpop(..., timeout=0) 永久静默阻塞，容易被中间网络/NAT 掐断；
       改为每 30s 唤醒一次，并在遇到 Redis/网络异常时退避重连，绝不拖垮同进程中的运行任务。
    """

    brpop_timeout_seconds: int = 30
    reconnect_backoff_seconds: float = 1.0

    async def listen(self) -> AsyncGenerator[bytes, None]:
        redis_brpop_data_position = 1
        while True:
            try:
                async with Redis(connection_pool=self.connection_pool) as redis_conn:
                    brpop_result = await redis_conn.brpop(
                        self.queue_name,
                        timeout=self.brpop_timeout_seconds,
                    )
                    if brpop_result is None:
                        continue
                    yield brpop_result[redis_brpop_data_position]  # type: ignore[misc]
            except asyncio.CancelledError:
                raise
            except (RedisError, ConnectionError, OSError) as exc:
                structlog.get_logger(__name__).warning(
                    "redis_broker_listen_reconnecting",
                    queue=self.queue_name,
                    error=str(exc),
                )
                await asyncio.sleep(self.reconnect_backoff_seconds)
                continue


ai_broker = ResilientListQueueBroker(
    url=settings.redis_url.get_secret_value(),
    queue_name=f"{settings.redis_key_prefix}queue:ai_io",
    socket_timeout=None,
    socket_connect_timeout=5,
    socket_keepalive=True,
    health_check_interval=30,
)

media_broker = ResilientListQueueBroker(
    url=settings.redis_url.get_secret_value(),
    queue_name=f"{settings.redis_key_prefix}queue:media_cpu",
    socket_timeout=None,
    socket_connect_timeout=5,
    socket_keepalive=True,
    health_check_interval=30,
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
        health_check_interval=30,
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
