from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.schemas import CamelModel


class CreditBalanceOut(CamelModel):
    balance: Decimal
    frozen: Decimal
    usage_multiplier: Decimal


class CreditLedgerOut(CamelModel):
    id: UUID
    operation: str
    balance_change: Decimal
    frozen_change: Decimal
    balance_before: Decimal
    balance_after: Decimal
    frozen_before: Decimal
    frozen_after: Decimal
    job_id: UUID | None = None
    reservation_id: UUID | None = None
    token_usage: dict[str, Any] | None = None
    reason: str
    created_at: datetime


class CreditLedgerListOut(CamelModel):
    items: list[CreditLedgerOut]
    total: int
