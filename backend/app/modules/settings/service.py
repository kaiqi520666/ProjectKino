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
