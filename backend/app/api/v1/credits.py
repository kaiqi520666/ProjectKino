from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import ApiResponse
from app.db.session import get_session
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.credits.schemas import CreditBalanceOut, CreditLedgerListOut, CreditLedgerOut
from app.modules.credits.service import list_user_ledgers

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


@router.get("/ledgers", response_model=ApiResponse[CreditLedgerListOut])
async def get_ledgers(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CreditLedgerListOut]:
    rows, total = await list_user_ledgers(session, user_id=user.id, limit=limit, offset=offset)
    return ApiResponse(
        data=CreditLedgerListOut(
            items=[CreditLedgerOut.model_validate(row) for row in rows],
            total=total,
        )
    )
