from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.auth.models import User
from app.modules.catalog.models import TextModelPrice
from app.modules.credits.models import CreditLedger, CreditReservation

_QUANT = Decimal("0.0001")
_ONE_MILLION = Decimal("1000000")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANT, rounding=ROUND_HALF_UP)


async def _lock_user(session: AsyncSession, user_id: int) -> User:
    user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise AppError(404, "user_not_found", "用户不存在")
    return user


def calculate_llm_token_cost(
    *,
    input_tokens: int,
    cache_read_tokens: int,
    output_tokens: int,
    price: TextModelPrice,
    usage_multiplier: Decimal,
) -> Decimal:
    """按 DeepSeek 真实返回的 token 计算积分消耗（未命中输入 + 缓存命中输入 + 输出）× 倍率。"""
    uncached_input = max(0, int(input_tokens) - max(0, int(cache_read_tokens)))
    cached_input = max(0, int(cache_read_tokens))
    out_tokens = max(0, int(output_tokens))

    raw = (
        Decimal(uncached_input) * price.input_price_per_million
        + Decimal(cached_input) * price.cached_input_price_per_million
        + Decimal(out_tokens) * price.output_price_per_million
    ) / _ONE_MILLION
    cost = _q(raw * usage_multiplier)
    return max(Decimal("0.0000"), cost)


async def assert_llm_balance_positive(session: AsyncSession, user_id: int) -> User:
    """LLM 调用前置检查：不预冻结，只要 balance > 0 即可放行；<= 0 时拒绝。"""
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise AppError(404, "user_not_found", "用户不存在")
    if user.balance <= Decimal("0"):
        raise AppError(402, "insufficient_credits", "积分余额不足，请充值后再继续调用")
    return user


async def grant_credits(
    session: AsyncSession,
    *,
    user_id: int,
    amount: Decimal,
    reason: str,
    idempotency_key: str,
    operation: str = "grant",
    operator_id: int | None = None,
) -> CreditLedger:
    existing = await session.scalar(
        select(CreditLedger).where(CreditLedger.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing

    delta = _q(amount)
    if operation == "grant" and delta <= 0:
        raise AppError(400, "invalid_credit_amount", "赠送积分必须大于 0")
    if operation == "adjust" and delta == 0:
        raise AppError(400, "invalid_credit_amount", "调账积分不能为 0")

    user = await _lock_user(session, user_id)
    balance_before = _q(user.balance)
    frozen_before = _q(user.frozen)
    balance_after = _q(balance_before + delta)
    user.balance = balance_after

    ledger = CreditLedger(
        user_id=user.id,
        operator_id=operator_id,
        idempotency_key=idempotency_key,
        operation=operation,
        balance_change=delta,
        frozen_change=Decimal("0.0000"),
        balance_before=balance_before,
        balance_after=balance_after,
        frozen_before=frozen_before,
        frozen_after=frozen_before,
        reason=reason,
    )
    session.add(ledger)
    await session.flush()
    return ledger


async def charge_llm_usage(
    session: AsyncSession,
    *,
    user_id: int,
    model_id: str,
    job_id: UUID | None,
    input_tokens: int,
    cache_read_tokens: int,
    output_tokens: int,
    idempotency_key: str,
    reason: str,
) -> CreditLedger | None:
    """
    DeepSeek 事后按真实 token 扣费：
    - 幂等：同一个 idempotency_key 不会重复扣费；
    - 零垫资：允许将 user.balance 扣成负数。
    """
    existing = await session.scalar(
        select(CreditLedger).where(CreditLedger.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing

    total_tokens = max(0, input_tokens) + max(0, output_tokens)
    if total_tokens == 0:
        return None

    price = await session.scalar(select(TextModelPrice).where(TextModelPrice.model_id == model_id))
    if price is None:
        raise AppError(500, "model_price_missing", f"未配置文本模型 {model_id} 的 Token 单价")

    user = await _lock_user(session, user_id)
    cost = calculate_llm_token_cost(
        input_tokens=input_tokens,
        cache_read_tokens=cache_read_tokens,
        output_tokens=output_tokens,
        price=price,
        usage_multiplier=user.usage_multiplier,
    )

    balance_before = _q(user.balance)
    frozen_before = _q(user.frozen)
    balance_change = -cost
    balance_after = _q(balance_before + balance_change)
    user.balance = balance_after

    ledger = CreditLedger(
        user_id=user.id,
        job_id=job_id,
        idempotency_key=idempotency_key,
        operation="llm_consume",
        balance_change=balance_change,
        frozen_change=Decimal("0.0000"),
        balance_before=balance_before,
        balance_after=balance_after,
        frozen_before=frozen_before,
        frozen_after=frozen_before,
        token_usage={
            "modelId": model_id,
            "inputTokens": max(0, input_tokens),
            "cacheReadTokens": max(0, cache_read_tokens),
            "outputTokens": max(0, output_tokens),
            "usageMultiplier": str(user.usage_multiplier),
            "cost": str(cost),
        },
        reason=reason,
    )
    session.add(ledger)
    await session.flush()
    return ledger


async def freeze_media_credits(
    session: AsyncSession,
    *,
    user_id: int,
    business_type: str,
    business_id: UUID,
    model_id: str,
    amount: Decimal,
    rate_snapshot: dict[str, Any],
    reason: str,
) -> CreditReservation:
    """图片/视频提交时预冻结积分（必须 balance >= amount）。"""
    existing = await session.scalar(
        select(CreditReservation).where(
            CreditReservation.business_type == business_type,
            CreditReservation.business_id == business_id,
        )
    )
    if existing is not None:
        return existing

    freeze_amount = _q(amount)
    if freeze_amount < 0:
        raise AppError(400, "invalid_credit_amount", "冻结积分不能为负数")

    user = await _lock_user(session, user_id)
    balance_before = _q(user.balance)
    frozen_before = _q(user.frozen)
    if balance_before < freeze_amount:
        raise AppError(
            402, "insufficient_credits", f"积分不足：需要 {freeze_amount}，当前可用 {balance_before}"
        )

    balance_after = _q(balance_before - freeze_amount)
    frozen_after = _q(frozen_before + freeze_amount)
    user.balance = balance_after
    user.frozen = frozen_after

    reservation = CreditReservation(
        user_id=user.id,
        business_type=business_type,
        business_id=business_id,
        model_id=model_id,
        amount=freeze_amount,
        consumed=None,
        status="frozen",
        rate_snapshot=rate_snapshot,
    )
    session.add(reservation)
    await session.flush()

    ledger = CreditLedger(
        user_id=user.id,
        reservation_id=reservation.id,
        job_id=business_id,
        idempotency_key=f"freeze:{business_type}:{business_id}",
        operation="freeze",
        balance_change=-freeze_amount,
        frozen_change=freeze_amount,
        balance_before=balance_before,
        balance_after=balance_after,
        frozen_before=frozen_before,
        frozen_after=frozen_after,
        reason=reason,
    )
    session.add(ledger)
    await session.flush()
    return reservation


async def settle_media_credits(
    session: AsyncSession,
    *,
    reservation_id: UUID,
    reason: str,
) -> CreditReservation:
    reservation = await session.scalar(
        select(CreditReservation).where(CreditReservation.id == reservation_id).with_for_update()
    )
    if reservation is None:
        raise AppError(404, "reservation_not_found", "冻结记录不存在")
    if reservation.status == "settled":
        return reservation
    if reservation.status != "frozen":
        raise AppError(409, "reservation_not_frozen", f"冻结记录当前状态为 {reservation.status}，无法结算")

    user = await _lock_user(session, reservation.user_id)
    amount = _q(reservation.amount)
    balance_before = _q(user.balance)
    frozen_before = _q(user.frozen)
    frozen_after = _q(frozen_before - amount)
    if frozen_after < 0:
        raise AppError(500, "frozen_underflow", "用户冻结余额异常，无法结算")

    user.frozen = frozen_after
    reservation.status = "settled"
    reservation.consumed = amount

    ledger = CreditLedger(
        user_id=user.id,
        reservation_id=reservation.id,
        job_id=reservation.business_id,
        idempotency_key=f"settle:{reservation.id}",
        operation="settle",
        balance_change=Decimal("0.0000"),
        frozen_change=-amount,
        balance_before=balance_before,
        balance_after=balance_before,
        frozen_before=frozen_before,
        frozen_after=frozen_after,
        reason=reason,
    )
    session.add(ledger)
    await session.flush()
    return reservation


async def release_media_credits(
    session: AsyncSession,
    *,
    reservation_id: UUID,
    reason: str,
) -> CreditReservation:
    reservation = await session.scalar(
        select(CreditReservation).where(CreditReservation.id == reservation_id).with_for_update()
    )
    if reservation is None:
        raise AppError(404, "reservation_not_found", "冻结记录不存在")
    if reservation.status == "released":
        return reservation
    if reservation.status != "frozen":
        raise AppError(409, "reservation_not_frozen", f"冻结记录当前状态为 {reservation.status}，无法释放")

    user = await _lock_user(session, reservation.user_id)
    amount = _q(reservation.amount)
    balance_before = _q(user.balance)
    frozen_before = _q(user.frozen)
    frozen_after = _q(frozen_before - amount)
    if frozen_after < 0:
        raise AppError(500, "frozen_underflow", "用户冻结余额异常，无法释放")

    balance_after = _q(balance_before + amount)
    user.balance = balance_after
    user.frozen = frozen_after
    reservation.status = "released"
    reservation.consumed = Decimal("0.0000")

    ledger = CreditLedger(
        user_id=user.id,
        reservation_id=reservation.id,
        job_id=reservation.business_id,
        idempotency_key=f"release:{reservation.id}",
        operation="release",
        balance_change=amount,
        frozen_change=-amount,
        balance_before=balance_before,
        balance_after=balance_after,
        frozen_before=frozen_before,
        frozen_after=frozen_after,
        reason=reason,
    )
    session.add(ledger)
    await session.flush()
    return reservation


async def list_user_ledgers(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[CreditLedger], int]:
    total = int(
        await session.scalar(
            select(func.count()).select_from(CreditLedger).where(CreditLedger.user_id == user_id)
        )
        or 0
    )
    rows = list(
        await session.scalars(
            select(CreditLedger)
            .where(CreditLedger.user_id == user_id)
            .order_by(desc(CreditLedger.created_at), desc(CreditLedger.id))
            .limit(max(1, min(limit, 100)))
            .offset(max(0, offset))
        )
    )
    return rows, total
