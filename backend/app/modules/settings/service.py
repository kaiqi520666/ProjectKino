from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.settings.models import SystemSetting

DEFAULT_REGISTRATION_SETTINGS: dict[str, Any] = {
    "initial_credits": "0.0000",
    "default_usage_multiplier": "1.0000",
}

DEFAULT_OSS_SETTINGS: dict[str, Any] = {
    "endpoint": "",
    "bucket": "",
    "access_key_id": "",
    "access_key_secret": "",
    "public_base_url": "",
    "prefix": "framedrama",
    "timeout_seconds": 30,
}

DEFAULT_REDEEM_SETTINGS: dict[str, Any] = {
    "purchase_url": "",
}


async def get_setting(
    session: AsyncSession,
    key: str,
    default: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = await session.scalar(select(SystemSetting).where(SystemSetting.key == key))
    base = dict(default or {})
    if row is not None and isinstance(row.value, dict):
        base.update(row.value)
    return base


async def upsert_setting(
    session: AsyncSession,
    key: str,
    value: dict[str, Any],
) -> SystemSetting:
    row = await session.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if row is None:
        row = SystemSetting(key=key, value=dict(value))
        session.add(row)
    else:
        row.value = dict(value)
    await session.flush()
    return row


async def get_registration_policy(session: AsyncSession) -> tuple[Decimal, Decimal]:
    cfg = await get_setting(session, "registration", DEFAULT_REGISTRATION_SETTINGS)
    initial_credits = Decimal(str(cfg.get("initial_credits", "0")))
    multiplier = Decimal(str(cfg.get("default_usage_multiplier", "1")))
    if initial_credits < 0:
        initial_credits = Decimal("0")
    if multiplier <= 0:
        multiplier = Decimal("1")
    return initial_credits, multiplier


async def get_redeem_purchase_url(session: AsyncSession) -> str:
    cfg = await get_setting(session, "redeem", DEFAULT_REDEEM_SETTINGS)
    raw = str(cfg.get("purchase_url") or "").strip()
    if raw and raw.startswith(("http://", "https://")):
        return raw
    return ""


async def set_redeem_purchase_url(session: AsyncSession, url: str) -> str:
    cleaned = url.strip()
    if cleaned:
        if len(cleaned) > 500 or not cleaned.startswith(("http://", "https://")):
            from app.core.errors import AppError

            raise AppError(400, "invalid_purchase_url", "购买链接必须以 http:// 或 https:// 开头")
    await upsert_setting(session, "redeem", {"purchase_url": cleaned})
    return cleaned
