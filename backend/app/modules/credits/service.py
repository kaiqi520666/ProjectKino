from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.auth.models import User
from app.modules.canvas.models import Canvas
from app.modules.catalog.models import AiModel, TextModelPrice
from app.modules.credits.models import CreditLedger, CreditReservation
from app.modules.credits.schemas import (
    CreditBillItemOut,
    CreditBillTimelineEventOut,
    CreditBreakdownOut,
    CreditLedgerOut,
    CreditSummaryOut,
    FrozenReservationItemOut,
)
from app.modules.jobs.models import Job
from app.modules.settings.service import get_redeem_purchase_url
from app.modules.studio.models import Project

_QUANT = Decimal("0.0001")
_ONE_MILLION = Decimal("1000000")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANT, rounding=ROUND_HALF_UP)


async def _lock_user(session: AsyncSession, user_id: int) -> User:
    user = await session.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
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
    if operation in ("grant", "redeem") and delta <= 0:
        raise AppError(400, "invalid_credit_amount", "入账积分必须大于 0")
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
        select(CreditReservation)
        .where(CreditReservation.id == reservation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
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
        select(CreditReservation)
        .where(CreditReservation.id == reservation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
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


_BILL_JOB_TITLES: dict[str, str] = {
    "script_generate": "生成全剧剧本",
    "script_regenerate": "重生成全剧剧本",
    "episode_rewrite": "重写单集剧本",
    "episode_append": "续写新分集",
    "assets_extract": "提取项目资产",
    "asset_image": "生成资产图片",
    "storyboard_generate": "生成单集分镜",
    "clip_video": "生成分镜视频",
    "episode_compose": "合成本集视频",
    "canvas_text": "画布文本生成",
    "canvas_image": "画布生图",
    "canvas_video": "画布生视频",
}


def _extract_ledger_model_id(
    ledger: CreditLedger,
    reservation: CreditReservation | None,
) -> str | None:
    if reservation is not None and reservation.model_id:
        return reservation.model_id
    usage = ledger.token_usage
    if isinstance(usage, dict):
        raw = usage.get("modelId") or usage.get("model")
        if raw:
            return str(raw)
    return None


def _resolve_ledger_business_type(
    ledger: CreditLedger,
    reservation: CreditReservation | None,
) -> Literal["text", "image", "video", "income"]:
    if reservation is not None:
        return "video" if reservation.business_type == "video" else "image"
    if ledger.operation == "llm_consume":
        return "text"
    return "income"


def _build_ledger_keyword_clause(keyword: str | None):
    cleaned = (keyword or "").strip()
    if not cleaned:
        return None
    pattern = f"%{cleaned}%"
    return or_(
        CreditLedger.reason.ilike(pattern),
        Project.name.ilike(pattern),
        Canvas.name.ilike(pattern),
        AiModel.display_name.ilike(pattern),
        CreditReservation.model_id.ilike(pattern),
    )


async def _load_ledger_context(
    session: AsyncSession,
    ledgers: list[CreditLedger],
) -> tuple[
    dict[UUID, CreditReservation],
    dict[UUID, Job],
    dict[UUID, str],
    dict[UUID, str],
    dict[str, str],
]:
    res_ids = {row.reservation_id for row in ledgers if row.reservation_id is not None}
    reservations_by_id: dict[UUID, CreditReservation] = {}
    if res_ids:
        reservations_by_id = {
            row.id: row
            for row in await session.scalars(
                select(CreditReservation).where(CreditReservation.id.in_(res_ids))
            )
        }

    job_ids = {row.job_id for row in ledgers if row.job_id is not None}
    for res in reservations_by_id.values():
        job_ids.add(res.business_id)
    jobs_by_id: dict[UUID, Job] = {}
    if job_ids:
        jobs_by_id = {
            row.id: row
            for row in await session.scalars(select(Job).where(Job.id.in_(job_ids)))
        }

    project_ids = {job.project_id for job in jobs_by_id.values() if job.project_id is not None}
    projects_by_id: dict[UUID, str] = {}
    if project_ids:
        projects_by_id = {
            row[0]: row[1]
            for row in (
                await session.execute(
                    select(Project.id, Project.name).where(Project.id.in_(project_ids))
                )
            ).all()
        }

    canvas_ids = {job.canvas_id for job in jobs_by_id.values() if job.canvas_id is not None}
    canvases_by_id: dict[UUID, str] = {}
    if canvas_ids:
        canvases_by_id = {
            row[0]: row[1]
            for row in (
                await session.execute(
                    select(Canvas.id, Canvas.name).where(Canvas.id.in_(canvas_ids))
                )
            ).all()
        }

    model_ids: set[str] = set()
    for ledger in ledgers:
        res = reservations_by_id.get(ledger.reservation_id) if ledger.reservation_id else None
        mid = _extract_ledger_model_id(ledger, res)
        if mid:
            model_ids.add(mid)
    models_by_id: dict[str, str] = {}
    if model_ids:
        models_by_id = {
            row[0]: row[1]
            for row in (
                await session.execute(
                    select(AiModel.id, AiModel.display_name).where(AiModel.id.in_(model_ids))
                )
            ).all()
        }

    return reservations_by_id, jobs_by_id, projects_by_id, canvases_by_id, models_by_id


def _serialize_enriched_ledger(
    ledger: CreditLedger,
    *,
    reservations_by_id: dict[UUID, CreditReservation],
    jobs_by_id: dict[UUID, Job],
    projects_by_id: dict[UUID, str],
    canvases_by_id: dict[UUID, str],
    models_by_id: dict[str, str],
) -> CreditLedgerOut:
    res = reservations_by_id.get(ledger.reservation_id) if ledger.reservation_id else None
    job_key = ledger.job_id or (res.business_id if res else None)
    job = jobs_by_id.get(job_key) if job_key else None
    model_id = _extract_ledger_model_id(ledger, res)
    return CreditLedgerOut(
        id=ledger.id,
        operation=ledger.operation,
        balance_change=ledger.balance_change,
        frozen_change=ledger.frozen_change,
        balance_before=ledger.balance_before,
        balance_after=ledger.balance_after,
        frozen_before=ledger.frozen_before,
        frozen_after=ledger.frozen_after,
        job_id=job_key,
        reservation_id=ledger.reservation_id,
        token_usage=ledger.token_usage,
        reason=ledger.reason,
        created_at=ledger.created_at,
        business_type=_resolve_ledger_business_type(ledger, res),
        model_id=model_id,
        model_name=models_by_id.get(model_id) if model_id else None,
        job_type=job.job_type if job else None,
        job_status=job.status if job else None,
        project_id=job.project_id if job else None,
        project_name=projects_by_id.get(job.project_id) if job and job.project_id else None,
        canvas_id=job.canvas_id if job else None,
        canvas_name=canvases_by_id.get(job.canvas_id) if job and job.canvas_id else None,
        rate_snapshot=res.rate_snapshot if res and res.rate_snapshot else None,
    )


async def list_enriched_user_ledgers(
    session: AsyncSession,
    *,
    user_id: int,
    operation: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    keyword: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> tuple[list[CreditLedgerOut], int]:
    conditions = [CreditLedger.user_id == user_id]
    if operation:
        conditions.append(CreditLedger.operation == operation)
    if start_at is not None:
        conditions.append(CreditLedger.created_at >= start_at)
    if end_at is not None:
        conditions.append(CreditLedger.created_at < end_at)

    kw_clause = _build_ledger_keyword_clause(keyword)
    base_from = select(CreditLedger.id).select_from(CreditLedger)
    if kw_clause is not None:
        base_from = (
            base_from.outerjoin(
                CreditReservation, CreditLedger.reservation_id == CreditReservation.id
            )
            .outerjoin(Job, CreditLedger.job_id == Job.id)
            .outerjoin(Project, Job.project_id == Project.id)
            .outerjoin(Canvas, Job.canvas_id == Canvas.id)
            .outerjoin(AiModel, CreditReservation.model_id == AiModel.id)
        )
        conditions.append(kw_clause)

    total = int(
        await session.scalar(
            select(func.count()).select_from(base_from.where(*conditions).subquery())
        )
        or 0
    )
    if total == 0:
        return [], 0

    id_stmt = (
        base_from.where(*conditions)
        .order_by(desc(CreditLedger.created_at), desc(CreditLedger.id))
        .limit(max(1, min(limit, 100)))
        .offset(max(0, offset))
    )
    page_ids = list(await session.scalars(id_stmt))
    if not page_ids:
        return [], total

    rows_by_id = {
        row.id: row
        for row in await session.scalars(select(CreditLedger).where(CreditLedger.id.in_(page_ids)))
    }
    ordered_rows = [rows_by_id[lid] for lid in page_ids if lid in rows_by_id]
    res_map, job_map, proj_map, canvas_map, model_map = await _load_ledger_context(
        session, ordered_rows
    )
    items = [
        _serialize_enriched_ledger(
            row,
            reservations_by_id=res_map,
            jobs_by_id=job_map,
            projects_by_id=proj_map,
            canvases_by_id=canvas_map,
            models_by_id=model_map,
        )
        for row in ordered_rows
    ]
    return items, total


def _build_bill_title(
    ledger: CreditLedger,
    job: Job | None,
    reservation: CreditReservation | None,
) -> str:
    if job is not None:
        if job.job_type == "asset_image" and isinstance(job.input_payload, dict):
            if job.input_payload.get("action") == "clip_storyboard_grid":
                return "生成分镜宫格图"
        if job.job_type in _BILL_JOB_TITLES:
            return _BILL_JOB_TITLES[job.job_type]
    if reservation is not None:
        return "视频生成" if reservation.business_type == "video" else "图片生成"
    if ledger.operation == "llm_consume":
        return "文本模型调用"
    if ledger.operation == "grant":
        return "积分赠送"
    if ledger.operation == "redeem":
        return "兑换码充值"
    if ledger.operation == "adjust":
        return "管理员调账"
    return ledger.reason or "积分变动"


def build_credit_bill_item(
    ledger: CreditLedger,
    *,
    reservation: CreditReservation | None,
    paired_ledgers: list[CreditLedger],
    job: Job | None,
    project_name: str | None,
    canvas_name: str | None,
    model_name: str | None,
) -> CreditBillItemOut:
    category = _resolve_ledger_business_type(ledger, reservation)
    model_id = _extract_ledger_model_id(ledger, reservation)
    timeline_rows = sorted(
        [ledger, *paired_ledgers],
        key=lambda item: (item.created_at, item.id),
    )
    timeline = [
        CreditBillTimelineEventOut(
            operation=item.operation,
            balance_change=item.balance_change,
            frozen_change=item.frozen_change,
            reason=item.reason,
            created_at=item.created_at,
        )
        for item in timeline_rows
    ]

    settled_at: datetime | None = None
    balance_after = ledger.balance_after
    if reservation is not None:
        original_amount = _q(reservation.amount)
        terminal = next(
            (item for item in reversed(paired_ledgers) if item.operation in ("settle", "release")),
            None,
        )
        if terminal is not None:
            settled_at = terminal.created_at
            balance_after = terminal.balance_after
        if reservation.status == "settled":
            status: Literal["charged", "frozen", "refunded", "credited"] = "charged"
            paid = reservation.consumed if reservation.consumed is not None else reservation.amount
            amount = -_q(paid)
        elif reservation.status == "released":
            status = "refunded"
            amount = Decimal("0.0000")
        else:
            status = "frozen"
            amount = -original_amount
    elif ledger.operation == "llm_consume":
        status = "charged"
        amount = _q(ledger.balance_change)
        original_amount = abs(amount)
        settled_at = ledger.created_at
    else:
        amount = _q(ledger.balance_change)
        original_amount = abs(amount)
        status = "credited" if amount >= 0 else "charged"
        settled_at = ledger.created_at

    return CreditBillItemOut(
        id=ledger.id,
        category=category,
        status=status,
        amount=amount,
        original_amount=original_amount,
        balance_after=balance_after,
        title=_build_bill_title(ledger, job, reservation),
        reason=ledger.reason,
        operation=ledger.operation,
        job_id=ledger.job_id or (reservation.business_id if reservation else None),
        reservation_id=ledger.reservation_id,
        job_type=job.job_type if job else None,
        job_status=job.status if job else None,
        model_id=model_id,
        model_name=model_name,
        project_id=job.project_id if job else None,
        project_name=project_name,
        canvas_id=job.canvas_id if job else None,
        canvas_name=canvas_name,
        token_usage=ledger.token_usage,
        rate_snapshot=reservation.rate_snapshot if reservation and reservation.rate_snapshot else None,
        created_at=ledger.created_at,
        settled_at=settled_at,
        timeline=timeline,
    )


async def list_user_bills(
    session: AsyncSession,
    *,
    user_id: int,
    category: Literal["text", "image", "video", "income"] | None = None,
    status: Literal["charged", "frozen", "refunded", "credited"] | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    keyword: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[CreditBillItemOut], int]:
    conditions = [
        CreditLedger.user_id == user_id,
        CreditLedger.operation.in_(("freeze", "llm_consume", "grant", "adjust", "redeem")),
    ]
    if start_at is not None:
        conditions.append(CreditLedger.created_at >= start_at)
    if end_at is not None:
        conditions.append(CreditLedger.created_at < end_at)

    if category == "text":
        conditions.append(CreditLedger.operation == "llm_consume")
    elif category == "image":
        conditions.append(
            and_(CreditLedger.operation == "freeze", CreditReservation.business_type == "image")
        )
    elif category == "video":
        conditions.append(
            and_(CreditLedger.operation == "freeze", CreditReservation.business_type == "video")
        )
    elif category == "income":
        conditions.append(CreditLedger.operation.in_(("grant", "adjust", "redeem")))

    if status == "frozen":
        conditions.append(
            and_(CreditLedger.operation == "freeze", CreditReservation.status == "frozen")
        )
    elif status == "refunded":
        conditions.append(
            and_(CreditLedger.operation == "freeze", CreditReservation.status == "released")
        )
    elif status == "credited":
        conditions.append(
            and_(
                CreditLedger.operation.in_(("grant", "adjust", "redeem")),
                CreditLedger.balance_change >= 0,
            )
        )
    elif status == "charged":
        conditions.append(
            or_(
                CreditLedger.operation == "llm_consume",
                and_(CreditLedger.operation == "freeze", CreditReservation.status == "settled"),
                and_(CreditLedger.operation == "adjust", CreditLedger.balance_change < 0),
            )
        )

    kw_clause = _build_ledger_keyword_clause(keyword)
    base_from = (
        select(CreditLedger.id)
        .select_from(CreditLedger)
        .outerjoin(CreditReservation, CreditLedger.reservation_id == CreditReservation.id)
    )
    if kw_clause is not None:
        base_from = (
            base_from.outerjoin(Job, CreditLedger.job_id == Job.id)
            .outerjoin(Project, Job.project_id == Project.id)
            .outerjoin(Canvas, Job.canvas_id == Canvas.id)
            .outerjoin(AiModel, CreditReservation.model_id == AiModel.id)
        )
        conditions.append(kw_clause)

    total = int(
        await session.scalar(
            select(func.count()).select_from(base_from.where(*conditions).subquery())
        )
        or 0
    )
    if total == 0:
        return [], 0

    page_ids = list(
        await session.scalars(
            base_from.where(*conditions)
            .order_by(desc(CreditLedger.created_at), desc(CreditLedger.id))
            .limit(max(1, min(limit, 100)))
            .offset(max(0, offset))
        )
    )
    if not page_ids:
        return [], total

    rows_by_id = {
        row.id: row
        for row in await session.scalars(select(CreditLedger).where(CreditLedger.id.in_(page_ids)))
    }
    ordered_rows = [rows_by_id[lid] for lid in page_ids if lid in rows_by_id]
    res_map, job_map, proj_map, canvas_map, model_map = await _load_ledger_context(
        session, ordered_rows
    )

    paired_by_res: dict[UUID, list[CreditLedger]] = {}
    if res_map:
        paired_rows = list(
            await session.scalars(
                select(CreditLedger).where(
                    CreditLedger.reservation_id.in_(list(res_map.keys())),
                    CreditLedger.operation.in_(("settle", "release")),
                )
            )
        )
        for p_row in paired_rows:
            if p_row.reservation_id is not None:
                paired_by_res.setdefault(p_row.reservation_id, []).append(p_row)

    bills: list[CreditBillItemOut] = []
    for row in ordered_rows:
        res = res_map.get(row.reservation_id) if row.reservation_id else None
        job_key = row.job_id or (res.business_id if res else None)
        job = job_map.get(job_key) if job_key else None
        model_id = _extract_ledger_model_id(row, res)
        bills.append(
            build_credit_bill_item(
                row,
                reservation=res,
                paired_ledgers=paired_by_res.get(row.reservation_id, []) if row.reservation_id else [],
                job=job,
                project_name=proj_map.get(job.project_id) if job and job.project_id else None,
                canvas_name=canvas_map.get(job.canvas_id) if job and job.canvas_id else None,
                model_name=model_map.get(model_id) if model_id else None,
            )
        )
    return bills, total


async def get_user_credit_summary(
    session: AsyncSession,
    *,
    user: User,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> CreditSummaryOut:
    time_conds = [CreditLedger.user_id == user.id]
    if start_at is not None:
        time_conds.append(CreditLedger.created_at >= start_at)
    if end_at is not None:
        time_conds.append(CreditLedger.created_at < end_at)

    text_spent_raw = await session.scalar(
        select(func.coalesce(func.sum(-CreditLedger.balance_change), 0)).where(
            *time_conds, CreditLedger.operation == "llm_consume"
        )
    )
    text_spent = _q(Decimal(str(text_spent_raw or 0)))

    media_rows = (
        await session.execute(
            select(
                CreditReservation.business_type,
                func.coalesce(func.sum(-CreditLedger.frozen_change), 0),
            )
            .join(CreditReservation, CreditLedger.reservation_id == CreditReservation.id)
            .where(*time_conds, CreditLedger.operation == "settle")
            .group_by(CreditReservation.business_type)
        )
    ).all()
    image_spent = Decimal("0.0000")
    video_spent = Decimal("0.0000")
    for biz_type, spent_val in media_rows:
        if biz_type == "image":
            image_spent = _q(Decimal(str(spent_val or 0)))
        elif biz_type == "video":
            video_spent = _q(Decimal(str(spent_val or 0)))

    granted_raw = await session.scalar(
        select(func.coalesce(func.sum(CreditLedger.balance_change), 0)).where(
            *time_conds,
            CreditLedger.operation.in_(("grant", "adjust", "redeem")),
            CreditLedger.balance_change > 0,
        )
    )
    total_granted = _q(Decimal(str(granted_raw or 0)))

    refunded_raw = await session.scalar(
        select(func.coalesce(func.sum(CreditLedger.balance_change), 0)).where(
            *time_conds,
            CreditLedger.operation == "release",
        )
    )
    total_refunded = _q(Decimal(str(refunded_raw or 0)))

    bill_count = int(
        await session.scalar(
            select(func.count(CreditLedger.id)).where(
                *time_conds,
                CreditLedger.operation.in_(("freeze", "llm_consume", "grant", "adjust", "redeem")),
            )
        )
        or 0
    )

    active_reservations = list(
        await session.scalars(
            select(CreditReservation)
            .where(
                CreditReservation.user_id == user.id,
                CreditReservation.status == "frozen",
            )
            .order_by(desc(CreditReservation.created_at), desc(CreditReservation.id))
            .limit(50)
        )
    )
    active_items: list[FrozenReservationItemOut] = []
    if active_reservations:
        res_ids = [r.id for r in active_reservations]
        job_ids = {r.business_id for r in active_reservations}
        model_ids = {r.model_id for r in active_reservations if r.model_id}

        jobs_by_id = {
            j.id: j for j in await session.scalars(select(Job).where(Job.id.in_(job_ids)))
        }
        project_ids = {j.project_id for j in jobs_by_id.values() if j.project_id is not None}
        canvas_ids = {j.canvas_id for j in jobs_by_id.values() if j.canvas_id is not None}

        projects_by_id: dict[UUID, str] = {}
        if project_ids:
            projects_by_id = {
                row[0]: row[1]
                for row in (
                    await session.execute(
                        select(Project.id, Project.name).where(Project.id.in_(project_ids))
                    )
                ).all()
            }
        canvases_by_id: dict[UUID, str] = {}
        if canvas_ids:
            canvases_by_id = {
                row[0]: row[1]
                for row in (
                    await session.execute(
                        select(Canvas.id, Canvas.name).where(Canvas.id.in_(canvas_ids))
                    )
                ).all()
            }
        models_by_id: dict[str, str] = {}
        if model_ids:
            models_by_id = {
                row[0]: row[1]
                for row in (
                    await session.execute(
                        select(AiModel.id, AiModel.display_name).where(AiModel.id.in_(model_ids))
                    )
                ).all()
            }
        reasons_by_res: dict[UUID, str] = {
            row[0]: row[1]
            for row in (
                await session.execute(
                    select(CreditLedger.reservation_id, CreditLedger.reason).where(
                        CreditLedger.reservation_id.in_(res_ids),
                        CreditLedger.operation == "freeze",
                    )
                )
            ).all()
            if row[0] is not None
        }

        for res in active_reservations:
            job = jobs_by_id.get(res.business_id)
            biz: Literal["image", "video"] = "video" if res.business_type == "video" else "image"
            active_items.append(
                FrozenReservationItemOut(
                    reservation_id=res.id,
                    business_type=biz,
                    amount=_q(res.amount),
                    model_id=res.model_id,
                    model_name=models_by_id.get(res.model_id),
                    job_id=res.business_id,
                    job_type=job.job_type if job else None,
                    job_status=job.status if job else None,
                    project_id=job.project_id if job else None,
                    project_name=projects_by_id.get(job.project_id) if job and job.project_id else None,
                    canvas_id=job.canvas_id if job else None,
                    canvas_name=canvases_by_id.get(job.canvas_id) if job and job.canvas_id else None,
                    rate_snapshot=res.rate_snapshot or {},
                    reason=reasons_by_res.get(res.id, ""),
                    created_at=res.created_at,
                )
            )

    redeem_purchase_url = await get_redeem_purchase_url(session)
    return CreditSummaryOut(
        balance=_q(user.balance),
        frozen=_q(user.frozen),
        usage_multiplier=user.usage_multiplier,
        total_spent=_q(text_spent + image_spent + video_spent),
        total_granted=total_granted,
        total_refunded=total_refunded,
        bill_count=bill_count,
        breakdown=CreditBreakdownOut(
            text_spent=text_spent,
            image_spent=image_spent,
            video_spent=video_spent,
        ),
        active_frozen_items=active_items,
        redeem_purchase_url=redeem_purchase_url,
    )
