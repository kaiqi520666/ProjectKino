from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
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
    # 富化溯源与计费元数据（可选，向后兼容）
    business_type: str | None = None
    model_id: str | None = None
    model_name: str | None = None
    job_type: str | None = None
    job_status: str | None = None
    project_id: UUID | None = None
    project_name: str | None = None
    canvas_id: UUID | None = None
    canvas_name: str | None = None
    rate_snapshot: dict[str, Any] | None = None


class CreditLedgerListOut(CamelModel):
    items: list[CreditLedgerOut]
    total: int


class CreditBillTimelineEventOut(CamelModel):
    operation: str
    balance_change: Decimal
    frozen_change: Decimal
    reason: str
    created_at: datetime


class CreditBillItemOut(CamelModel):
    id: UUID
    category: Literal["text", "image", "video", "income"]
    status: Literal["charged", "frozen", "refunded", "credited"]
    amount: Decimal
    original_amount: Decimal
    balance_after: Decimal
    title: str
    reason: str
    operation: str
    job_id: UUID | None = None
    reservation_id: UUID | None = None
    job_type: str | None = None
    job_status: str | None = None
    model_id: str | None = None
    model_name: str | None = None
    project_id: UUID | None = None
    project_name: str | None = None
    canvas_id: UUID | None = None
    canvas_name: str | None = None
    token_usage: dict[str, Any] | None = None
    rate_snapshot: dict[str, Any] | None = None
    created_at: datetime
    settled_at: datetime | None = None
    timeline: list[CreditBillTimelineEventOut] = []


class CreditBillListOut(CamelModel):
    items: list[CreditBillItemOut]
    total: int


class FrozenReservationItemOut(CamelModel):
    reservation_id: UUID
    business_type: Literal["image", "video"]
    amount: Decimal
    model_id: str
    model_name: str | None = None
    job_id: UUID
    job_type: str | None = None
    job_status: str | None = None
    project_id: UUID | None = None
    project_name: str | None = None
    canvas_id: UUID | None = None
    canvas_name: str | None = None
    rate_snapshot: dict[str, Any] = {}
    reason: str = ""
    created_at: datetime


class CreditBreakdownOut(CamelModel):
    text_spent: Decimal
    image_spent: Decimal
    video_spent: Decimal


class CreditSummaryOut(CamelModel):
    balance: Decimal
    frozen: Decimal
    usage_multiplier: Decimal
    total_spent: Decimal
    total_granted: Decimal
    total_refunded: Decimal
    bill_count: int
    breakdown: CreditBreakdownOut
    active_frozen_items: list[FrozenReservationItemOut]
