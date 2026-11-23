import asyncio
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from pydantic_ai.exceptions import ModelHTTPError

from app.core.errors import AppError

logger = structlog.get_logger(__name__)

_ACQUIRE_SLOT_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local expires_at = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local token = ARGV[4]
local key_ttl = tonumber(ARGV[5])

redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
local count = redis.call('ZCARD', key)
if count < limit then
    redis.call('ZADD', key, expires_at, token)
    redis.call('EXPIRE', key, key_ttl)
    return 1
end
return 0
"""

_RENEW_SLOT_LUA = """
local key = KEYS[1]
local expires_at = tonumber(ARGV[1])
local token = ARGV[2]
local key_ttl = tonumber(ARGV[3])

if redis.call('ZSCORE', key, token) then
    redis.call('ZADD', key, expires_at, token)
    redis.call('EXPIRE', key, key_ttl)
    return 1
end
return 0
"""

_LOCAL_FALLBACK_SEMAPHORES: dict[tuple[str, int], asyncio.Semaphore] = {}

RETRYABLE_HTTP_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
STEP_RETRY_BACKOFF_SECONDS = (5, 15, 30)


def retry_backoff_seconds(attempt: int) -> int:
    """Return exponential-style backoff delay in seconds for 1-based attempt number."""
    if attempt <= 0:
        return STEP_RETRY_BACKOFF_SECONDS[0]
    idx = min(attempt - 1, len(STEP_RETRY_BACKOFF_SECONDS) - 1)
    return STEP_RETRY_BACKOFF_SECONDS[idx]


def is_retryable_llm_error(exc: BaseException) -> bool:
    """Classify transient network / rate-limit / upstream 5xx failures safe for auto-retry."""
    if isinstance(exc, asyncio.CancelledError):
        return False
    if isinstance(exc, AppError):
        return exc.status_code in RETRYABLE_HTTP_STATUS_CODES
    if isinstance(exc, ModelHTTPError):
        return exc.status_code in RETRYABLE_HTTP_STATUS_CODES
    if isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
            TimeoutError,
            ConnectionError,
        ),
    ):
        return True
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and status_code in RETRYABLE_HTTP_STATUS_CODES:
        return True
    cause = exc.__cause__
    if cause is not None and cause is not exc:
        return is_retryable_llm_error(cause)
    return False


def _local_semaphore(scope: str, limit: int) -> asyncio.Semaphore:
    key = (scope, max(1, limit))
    sem = _LOCAL_FALLBACK_SEMAPHORES.get(key)
    if sem is None:
        sem = asyncio.Semaphore(key[1])
        _LOCAL_FALLBACK_SEMAPHORES[key] = sem
    return sem


@asynccontextmanager
async def acquire_llm_slot(
    redis: Any,
    settings: Any,
    model_id: str,
    *,
    poll_interval: float = 0.5,
) -> AsyncIterator[None]:
    """
    跨进程/多 Pod 共享的 Redis LLM 并发闸门（ZSET + TTL 租约）：
    - 防止多用户并发打爆上游模型 RPM/并发上限；
    - 每个槽位自带 TTL 且持有期间自动续租，Worker 异常强杀后自动过期，绝不死锁；
    - 单测 FakeRedis 无 eval 时自动降级为进程内 asyncio.Semaphore。
    """
    limit = max(1, int(getattr(settings, "llm_max_concurrency", 20) or 20))
    ttl_seconds = max(30, int(getattr(settings, "llm_slot_ttl_seconds", 240) or 240))
    prefix = str(getattr(settings, "redis_key_prefix", "framedrama:"))
    key = f"{prefix}llm_slots:{model_id or 'default'}"

    if redis is None or not callable(getattr(redis, "eval", None)):
        async with _local_semaphore(key, limit):
            yield
        return

    token = secrets.token_hex(12)
    key_ttl = ttl_seconds + 60
    acquired = False

    while not acquired:
        now = time.time()
        try:
            res = await redis.eval(
                _ACQUIRE_SLOT_LUA,
                1,
                key,
                now,
                now + ttl_seconds,
                limit,
                token,
                key_ttl,
            )
            if int(res or 0) == 1:
                acquired = True
                break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Redis 瞬时波动时退化到本地信号量，避免误阻塞所有任务。
            logger.warning("llm_slot_redis_fallback", key=key, error=str(exc))
            async with _local_semaphore(key, limit):
                yield
            return
        await asyncio.sleep(poll_interval)

    renew_interval = max(10.0, ttl_seconds / 3.0)

    async def _renew_loop() -> None:
        while True:
            await asyncio.sleep(renew_interval)
            try:
                now = time.time()
                await redis.eval(
                    _RENEW_SLOT_LUA,
                    1,
                    key,
                    now + ttl_seconds,
                    token,
                    key_ttl,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("llm_slot_renew_failed", key=key, error=str(exc))

    renew_task = asyncio.create_task(_renew_loop())
    try:
        yield
    finally:
        renew_task.cancel()
        try:
            await renew_task
        except asyncio.CancelledError:
            pass
        try:
            await redis.zrem(key, token)
        except Exception as exc:
            logger.warning("llm_slot_release_failed", key=key, error=str(exc))
