import re
import secrets
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.auth.models import User
from app.modules.credits.models import CreditLedger, RedeemCode, RedeemCodeUse
from app.modules.credits.schemas import (
    REDEEM_CREDIT_TIERS,
    AdminRedeemCodeItemOut,
    AdminRedeemCodeListOut,
    AdminRedeemCodeUseItemOut,
    AdminRedeemStatsOut,
)
from app.modules.credits.service import _q, grant_credits
from app.modules.settings.service import get_redeem_purchase_url

# 剔除易混淆字符 0 / O / 1 / I / L
REDEEM_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_ALLOWED_CREDIT_TIERS = frozenset(Decimal(v) for v in REDEEM_CREDIT_TIERS)
_REDEEM_FAIL_LIMIT = 10
_REDEEM_FAIL_WINDOW_SECONDS = 60


def normalize_redeem_code(raw: str) -> str:
    """去除空白、横杠与下划线并转大写，便于兼容粘贴格式。"""
    cleaned = re.sub(r"[\s\-_]+", "", raw.strip()).upper()
    return cleaned


def generate_random_code_str() -> str:
    """生成 20 位去歧义字母数字卡密（XXXX-XXXX-XXXX-XXXX-XXXX）。"""
    raw = "".join(secrets.choice(REDEEM_ALPHABET) for _ in range(20))
    return "-".join(raw[i : i + 4] for i in range(0, 20, 4))


def resolve_redeem_status(
    row: RedeemCode,
    now: datetime | None = None,
) -> Literal["active", "exhausted", "expired", "disabled"]:
    if row.status == "disabled":
        return "disabled"
    if row.used_count >= row.max_uses:
        return "exhausted"
    current = now or datetime.now(UTC)
    if row.expires_at is not None:
        exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
        if exp <= current:
            return "expired"
    return "active"


async def _check_redeem_rate_limit(redis: Any | None, settings: Any | None, user_id: int) -> None:
    if redis is None:
        return
    prefix = getattr(settings, "redis_key_prefix", "framedrama:")
    key = f"{prefix}redeem:fail:{user_id}"
    try:
        raw_count = await redis.get(key)
        if raw_count is not None and int(raw_count) >= _REDEEM_FAIL_LIMIT:
            raise AppError(429, "redeem_rate_limited", "尝试次数过多，请 1 分钟后再试")
    except AppError:
        raise
    except Exception:
        return


async def _record_redeem_failure(redis: Any | None, settings: Any | None, user_id: int) -> None:
    if redis is None:
        return
    prefix = getattr(settings, "redis_key_prefix", "framedrama:")
    key = f"{prefix}redeem:fail:{user_id}"
    try:
        count = await redis.incr(key)
        if int(count) == 1:
            await redis.expire(key, _REDEEM_FAIL_WINDOW_SECONDS)
    except Exception:
        return


async def _clear_redeem_failures(redis: Any | None, settings: Any | None, user_id: int) -> None:
    if redis is None:
        return
    prefix = getattr(settings, "redis_key_prefix", "framedrama:")
    key = f"{prefix}redeem:fail:{user_id}"
    try:
        await redis.delete(key)
    except Exception:
        return


async def generate_redeem_codes(
    session: AsyncSession,
    *,
    credits: Decimal,
    count: int,
    batch_name: str = "",
    max_uses: int = 1,
    expires_at: datetime | None = None,
    created_by: int | None = None,
) -> list[RedeemCode]:
    credit_amount = _q(credits)
    if credit_amount not in _ALLOWED_CREDIT_TIERS:
        tiers_text = "、".join(str(t) for t in REDEEM_CREDIT_TIERS)
        raise AppError(400, "invalid_credit_tier", f"面额积分仅支持：{tiers_text}")
    if count < 1 or count > 500:
        raise AppError(400, "invalid_code_count", "单次生成数量必须在 1–500 之间")
    if max_uses < 1:
        raise AppError(400, "invalid_max_uses", "可用次数必须大于等于 1")

    clean_batch = batch_name.strip()[:120]
    exp = expires_at
    if exp is not None and exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)

    candidates: dict[str, str] = {}
    attempts = 0
    max_attempts = count * 10
    while len(candidates) < count and attempts < max_attempts:
        attempts += 1
        display_code = generate_random_code_str()
        norm = normalize_redeem_code(display_code)
        if norm not in candidates:
            candidates[norm] = display_code

    existing = set(
        await session.scalars(
            select(RedeemCode.code_normalized).where(
                RedeemCode.code_normalized.in_(list(candidates.keys()))
            )
        )
    )
    for dup in existing:
        candidates.pop(dup, None)

    while len(candidates) < count and attempts < max_attempts * 2:
        attempts += 1
        display_code = generate_random_code_str()
        norm = normalize_redeem_code(display_code)
        if norm in candidates or norm in existing:
            continue
        exists_single = await session.scalar(
            select(RedeemCode.id).where(RedeemCode.code_normalized == norm)
        )
        if exists_single is not None:
            existing.add(norm)
            continue
        candidates[norm] = display_code

    if len(candidates) < count:
        raise AppError(500, "redeem_generation_failed", "生成唯一兑换码失败，请重试")

    rows = [
        RedeemCode(
            code=display_code,
            code_normalized=norm,
            batch_name=clean_batch,
            credits=credit_amount,
            max_uses=max_uses,
            used_count=0,
            status="active",
            expires_at=exp,
            created_by=created_by,
        )
        for norm, display_code in candidates.items()
    ]
    session.add_all(rows)
    await session.flush()
    return rows


async def redeem_code_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    raw_code: str,
    redis: Any | None = None,
    settings: Any | None = None,
) -> tuple[RedeemCode, CreditLedger]:
    await _check_redeem_rate_limit(redis, settings, user_id)

    norm = normalize_redeem_code(raw_code)
    if len(norm) < 4:
        await _record_redeem_failure(redis, settings, user_id)
        raise AppError(400, "invalid_redeem_code", "兑换码格式无效")

    code_row = await session.scalar(
        select(RedeemCode)
        .where(RedeemCode.code_normalized == norm)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if code_row is None:
        await _record_redeem_failure(redis, settings, user_id)
        raise AppError(404, "redeem_code_not_found", "兑换码无效或不存在")

    now = datetime.now(UTC)
    if code_row.status == "disabled":
        await _record_redeem_failure(redis, settings, user_id)
        raise AppError(400, "redeem_code_disabled", "该兑换码已作废")

    if code_row.expires_at is not None:
        exp = code_row.expires_at if code_row.expires_at.tzinfo else code_row.expires_at.replace(tzinfo=UTC)
        if exp <= now:
            await _record_redeem_failure(redis, settings, user_id)
            raise AppError(400, "redeem_code_expired", "该兑换码已过期")

    existing_use = await session.scalar(
        select(RedeemCodeUse.id).where(
            RedeemCodeUse.code_id == code_row.id,
            RedeemCodeUse.user_id == user_id,
        )
    )
    if existing_use is not None:
        raise AppError(409, "redeem_code_already_used_by_user", "您已兑换过该兑换码")

    if code_row.used_count >= code_row.max_uses:
        await _record_redeem_failure(redis, settings, user_id)
        raise AppError(409, "redeem_code_exhausted", "该兑换码已被使用")

    code_row.used_count += 1
    reason = f"兑换码充值（{code_row.batch_name}）" if code_row.batch_name else "兑换码充值"
    ledger = await grant_credits(
        session,
        user_id=user_id,
        amount=code_row.credits,
        reason=reason,
        idempotency_key=f"redeem:{code_row.id}:{user_id}",
        operation="redeem",
    )
    use_row = RedeemCodeUse(
        code_id=code_row.id,
        user_id=user_id,
        credits=code_row.credits,
        ledger_id=ledger.id,
    )
    session.add(use_row)
    await session.flush()
    await _clear_redeem_failures(redis, settings, user_id)
    return code_row, ledger


async def list_admin_redeem_codes(
    session: AsyncSession,
    *,
    status_filter: Literal["active", "exhausted", "expired", "disabled"] | None = None,
    credits_filter: Decimal | None = None,
    batch_name: str | None = None,
    keyword: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> AdminRedeemCodeListOut:
    now = datetime.now(UTC)
    conditions = []

    if credits_filter is not None:
        conditions.append(RedeemCode.credits == _q(credits_filter))

    clean_batch = (batch_name or "").strip()
    if clean_batch:
        conditions.append(RedeemCode.batch_name == clean_batch)

    clean_kw = (keyword or "").strip()
    if clean_kw:
        norm_kw = normalize_redeem_code(clean_kw)
        kw_clauses = [
            RedeemCode.code.ilike(f"%{clean_kw}%"),
            RedeemCode.batch_name.ilike(f"%{clean_kw}%"),
        ]
        if norm_kw:
            kw_clauses.append(RedeemCode.code_normalized.ilike(f"%{norm_kw}%"))
        conditions.append(or_(*kw_clauses))

    if status_filter == "disabled":
        conditions.append(RedeemCode.status == "disabled")
    elif status_filter == "exhausted":
        conditions.append(
            and_(RedeemCode.status == "active", RedeemCode.used_count >= RedeemCode.max_uses)
        )
    elif status_filter == "expired":
        conditions.append(
            and_(
                RedeemCode.status == "active",
                RedeemCode.used_count < RedeemCode.max_uses,
                RedeemCode.expires_at.is_not(None),
                RedeemCode.expires_at <= now,
            )
        )
    elif status_filter == "active":
        conditions.append(
            and_(
                RedeemCode.status == "active",
                RedeemCode.used_count < RedeemCode.max_uses,
                or_(RedeemCode.expires_at.is_(None), RedeemCode.expires_at > now),
            )
        )

    total = int(
        await session.scalar(select(func.count(RedeemCode.id)).where(*conditions)) or 0
    )
    rows = list(
        await session.scalars(
            select(RedeemCode)
            .where(*conditions)
            .order_by(desc(RedeemCode.created_at), desc(RedeemCode.id))
            .limit(max(1, min(limit, 100)))
            .offset(max(0, offset))
        )
    )

    total_codes = int(await session.scalar(select(func.count(RedeemCode.id))) or 0)
    active_codes = int(
        await session.scalar(
            select(func.count(RedeemCode.id)).where(
                RedeemCode.status == "active",
                RedeemCode.used_count < RedeemCode.max_uses,
                or_(RedeemCode.expires_at.is_(None), RedeemCode.expires_at > now),
            )
        )
        or 0
    )
    used_count_total = int(
        await session.scalar(select(func.coalesce(func.sum(RedeemCode.used_count), 0))) or 0
    )
    redeemed_credits_raw = await session.scalar(
        select(func.coalesce(func.sum(RedeemCodeUse.credits), 0))
    )
    redeemed_credits_total = _q(Decimal(str(redeemed_credits_raw or 0)))

    batch_rows = list(
        await session.scalars(
            select(RedeemCode.batch_name)
            .where(RedeemCode.batch_name != "")
            .distinct()
            .order_by(RedeemCode.batch_name)
            .limit(100)
        )
    )
    purchase_url = await get_redeem_purchase_url(session)

    items = [
        AdminRedeemCodeItemOut(
            id=row.id,
            code=row.code,
            batch_name=row.batch_name,
            credits=_q(row.credits),
            max_uses=row.max_uses,
            used_count=row.used_count,
            status=resolve_redeem_status(row, now),
            raw_status="disabled" if row.status == "disabled" else "active",
            expires_at=row.expires_at,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return AdminRedeemCodeListOut(
        items=items,
        total=total,
        stats=AdminRedeemStatsOut(
            total_codes=total_codes,
            active_codes=active_codes,
            used_count_total=used_count_total,
            redeemed_credits_total=redeemed_credits_total,
        ),
        batches=batch_rows,
        purchase_url=purchase_url,
        credit_tiers=list(REDEEM_CREDIT_TIERS),
    )


async def list_redeem_code_uses(
    session: AsyncSession,
    *,
    code_id: UUID,
) -> list[AdminRedeemCodeUseItemOut]:
    rows = (
        await session.execute(
            select(RedeemCodeUse, User.email, User.nickname)
            .join(User, RedeemCodeUse.user_id == User.id)
            .where(RedeemCodeUse.code_id == code_id)
            .order_by(desc(RedeemCodeUse.created_at))
            .limit(200)
        )
    ).all()
    return [
        AdminRedeemCodeUseItemOut(
            id=use_row.id,
            user_id=use_row.user_id,
            email=email,
            nickname=nickname,
            credits=_q(use_row.credits),
            created_at=use_row.created_at,
        )
        for use_row, email, nickname in rows
    ]


async def update_redeem_code_status(
    session: AsyncSession,
    *,
    code_id: UUID,
    status: Literal["active", "disabled"],
) -> RedeemCode:
    row = await session.scalar(select(RedeemCode).where(RedeemCode.id == code_id))
    if row is None:
        raise AppError(404, "redeem_code_not_found", "兑换码不存在")
    row.status = status
    await session.flush()
    return row


async def disable_redeem_batch(session: AsyncSession, *, batch_name: str) -> int:
    clean = batch_name.strip()
    if not clean:
        raise AppError(400, "invalid_batch_name", "请指定批次名称")
    result = await session.execute(
        update(RedeemCode)
        .where(
            RedeemCode.batch_name == clean,
            RedeemCode.status == "active",
            RedeemCode.used_count < RedeemCode.max_uses,
        )
        .values(status="disabled")
    )
    await session.flush()
    return int(result.rowcount or 0)
