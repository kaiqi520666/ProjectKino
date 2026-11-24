from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import ApiResponse
from app.db.session import get_session
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.credits.schemas import (
    CreditBalanceOut,
    CreditBillListOut,
    CreditLedgerListOut,
    CreditSummaryOut,
)
from app.modules.credits.service import (
    get_user_credit_summary,
    list_enriched_user_ledgers,
    list_user_bills,
)

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get("/balance", response_model=ApiResponse[CreditBalanceOut])
async def get_balance(user: User = Depends(get_current_user)) -> ApiResponse[CreditBalanceOut]:
    return ApiResponse(
        data=CreditBalanceOut(
            balance=user.balance,
            frozen=user.frozen,
            usage_multiplier=user.usage_multiplier,
        )
    )


@router.get("/summary", response_model=ApiResponse[CreditSummaryOut])
async def get_summary(
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CreditSummaryOut]:
    summary = await get_user_credit_summary(
        session,
        user=user,
        start_at=start_at,
        end_at=end_at,
    )
    return ApiResponse(data=summary)


@router.get("/bills", response_model=ApiResponse[CreditBillListOut])
async def get_bills(
    category: Literal["text", "image", "video", "income"] | None = Query(default=None),
    status: Literal["charged", "frozen", "refunded", "credited"] | None = Query(default=None),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    keyword: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CreditBillListOut]:
    items, total = await list_user_bills(
        session,
        user_id=user.id,
        category=category,
        status=status,
        start_at=start_at,
        end_at=end_at,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )
    return ApiResponse(data=CreditBillListOut(items=items, total=total))


@router.get("/ledgers", response_model=ApiResponse[CreditLedgerListOut])
async def get_ledgers(
    operation: Literal["grant", "freeze", "settle", "release", "llm_consume", "adjust"]
    | None = Query(default=None),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    keyword: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CreditLedgerListOut]:
    items, total = await list_enriched_user_ledgers(
        session,
        user_id=user.id,
        operation=operation,
        start_at=start_at,
        end_at=end_at,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )
    return ApiResponse(data=CreditLedgerListOut(items=items, total=total))
