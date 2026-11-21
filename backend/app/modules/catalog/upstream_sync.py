"""上游模型状态 5 分钟轮询监控器（基于 OpenAI 标准 GET /v1/models，仅监控已配置模型，仅记录变动）。"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import undefer

from app.modules.catalog.models import AiModel, AiModelSyncLog, AiProvider

logger = structlog.get_logger(__name__)


async def fetch_upstream_model_ids(
    *,
    base_url: str,
    api_key: str,
    http_client: httpx.AsyncClient | None = None,
    timeout_seconds: float = 15.0,
) -> set[str]:
    """
    请求上游标准 `GET {base_url}/models`（带 Bearer API Key），返回当前 Key 实际可用的模型 ID 集合。
    若网络异常、状态码非 200 或返回空列表则抛出 ValueError，由调用方熔断跳过本轮以防误杀。
    """
    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key.strip()}", "Accept": "application/json"}

    if http_client is not None:
        resp = await http_client.get(url, headers=headers, timeout=timeout_seconds)
    else:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
            resp = await client.get(url, headers=headers)

    if resp.status_code != 200:
        raise ValueError(f"upstream /v1/models returned HTTP {resp.status_code}")

    payload = resp.json()
    raw_items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list) or len(raw_items) == 0:
        raise ValueError("upstream /v1/models returned empty data list")

    ids = {
        str(item.get("id")).strip()
        for item in raw_items
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    if not ids:
        raise ValueError("upstream /v1/models returned no valid model ids")
    return ids


async def sync_provider_models_in_session(
    session: AsyncSession,
    *,
    provider_key: str = "cc",
    http_client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    在已有 AsyncSession 中对指定供应商执行一次上游可用性同步：
    - 仅监控本地 ai_models 中已添加的该供应商模型（忽略上游未录入的新模型）
    - 上游异常或返回空列表时熔断跳过，绝不误标下架
    - 仅在 upstream_available 发生状态切换时写入 ai_model_sync_logs
    """
    provider = await session.scalar(
        select(AiProvider)
        .options(undefer(AiProvider.api_key))
        .where(AiProvider.key == provider_key)
    )
    if provider is None:
        return {"providerKey": provider_key, "skipped": True, "reason": "provider_not_found"}
    if not provider.enabled or not (provider.api_key or "").strip() or not (provider.base_url or "").strip():
        return {"providerKey": provider_key, "skipped": True, "reason": "provider_not_configured"}

    models = list(
        await session.scalars(select(AiModel).where(AiModel.provider_id == provider.id))
    )
    if not models:
        return {"providerKey": provider_key, "checked": 0, "offline": 0, "restored": 0, "skipped": False}

    try:
        live_ids = await fetch_upstream_model_ids(
            base_url=provider.base_url,
            api_key=provider.api_key,
            http_client=http_client,
        )
    except Exception as exc:
        logger.warning("upstream_model_sync_skipped", provider=provider_key, error=str(exc))
        return {
            "providerKey": provider_key,
            "skipped": True,
            "reason": str(exc),
            "checked": len(models),
            "offline": 0,
            "restored": 0,
        }

    current = now or datetime.now(UTC)
    offline_count = 0
    restored_count = 0

    for model in models:
        is_online = model.upstream_model_id in live_ids
        model.last_synced_at = current
        if model.upstream_available and not is_online:
            model.upstream_available = False
            offline_count += 1
            session.add(
                AiModelSyncLog(
                    provider_key=provider.key,
                    model_id=model.id,
                    upstream_model_id=model.upstream_model_id,
                    event_type="offline",
                    summary=(
                        f"上游已下架 {model.upstream_model_id}（{model.display_name}），"
                        "前端已自动隐藏并禁止下单"
                    ),
                )
            )
        elif not model.upstream_available and is_online:
            model.upstream_available = True
            restored_count += 1
            session.add(
                AiModelSyncLog(
                    provider_key=provider.key,
                    model_id=model.id,
                    upstream_model_id=model.upstream_model_id,
                    event_type="restored",
                    summary=f"上游已恢复 {model.upstream_model_id}（{model.display_name}）",
                )
            )

    await session.commit()
    result = {
        "providerKey": provider.key,
        "skipped": False,
        "checked": len(models),
        "upstreamCount": len(live_ids),
        "offline": offline_count,
        "restored": restored_count,
    }
    if offline_count > 0 or restored_count > 0:
        logger.info("upstream_model_sync_changes", **result)
    return result


async def sync_provider_models_once(
    *,
    sessions: async_sessionmaker[AsyncSession],
    redis: Any,
    settings: Any,
    provider_key: str = "cc",
    http_client: httpx.AsyncClient | None = None,
    use_lock: bool = True,
) -> dict[str, Any]:
    if use_lock and redis is not None:
        lock_key = f"{settings.redis_key_prefix}upstream_sync:{provider_key}:lock"
        acquired = await redis.set(lock_key, "1", nx=True, ex=280)
        if not acquired:
            return {"providerKey": provider_key, "skipped": True, "reason": "locked"}

    async with sessions() as session:
        return await sync_provider_models_in_session(
            session,
            provider_key=provider_key,
            http_client=http_client,
        )


async def upstream_sync_loop(
    *,
    sessions: async_sessionmaker[AsyncSession],
    redis: Any,
    settings: Any,
    http_client: httpx.AsyncClient | None = None,
    provider_key: str = "cc",
    interval_seconds: float = 300.0,
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await sync_provider_models_once(
                sessions=sessions,
                redis=redis,
                settings=settings,
                provider_key=provider_key,
                http_client=http_client,
                use_lock=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("upstream_model_sync_loop_error", provider=provider_key)
