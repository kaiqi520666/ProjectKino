from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.core.schemas import CamelModel


class CreditBalanceOut(CamelModel):
    balance: Decimal
    frozen: Decimal
    usage_multiplier: Decimal
    redeem_purchase_url: str = ""


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
    redeem_purchase_url: str = ""


class RedeemCodeRequest(CamelModel):
    code: str = Field(min_length=1, max_length=64)


class RedeemCodeResultOut(CamelModel):
    credits: Decimal
    balance: Decimal
    batch_name: str = ""
    redeemed_at: datetime


class AdminRedeemBatchCreateRequest(CamelModel):
    credits: Decimal = Field(gt=0, le=Decimal("10000000"))
    count: int = Field(default=10, ge=1, le=500)
    prefix: str = Field(default="", max_length=12)
    batch_name: str = Field(default="", max_length=120)
    max_uses: int = Field(default=1, ge=1, le=100000)
    expires_at: datetime | None = None


class AdminRedeemCodeItemOut(CamelModel):
    id: UUID
    code: str
    batch_name: str
    credits: Decimal
    max_uses: int
    used_count: int
    status: Literal["active", "exhausted", "expired", "disabled"]
    raw_status: Literal["active", "disabled"]
    expires_at: datetime | None = None
    created_at: datetime


class AdminRedeemStatsOut(CamelModel):
    total_codes: int
    active_codes: int
    used_count_total: int
    redeemed_credits_total: Decimal


class AdminRedeemCodeListOut(CamelModel):
    items: list[AdminRedeemCodeItemOut]
    total: int
    stats: AdminRedeemStatsOut
    batches: list[str]
    purchase_url: str = ""


class AdminRedeemBatchCreateOut(CamelModel):
    count: int
    credits: Decimal
    batch_name: str
    codes: list[str]


class AdminRedeemCodeUseItemOut(CamelModel):
    id: UUID
    user_id: int
    email: str
    nickname: str
    credits: Decimal
    created_at: datetime


class AdminRedeemCodeUseListOut(CamelModel):
    items: list[AdminRedeemCodeUseItemOut]


class AdminRedeemCodeStatusUpdateRequest(CamelModel):
    status: Literal["active", "disabled"]


class AdminRedeemBatchDisableRequest(CamelModel):
    batch_name: str = Field(min_length=1, max_length=120)


class AdminRedeemPurchaseUrlUpdateRequest(CamelModel):
    purchase_url: str = Field(default="", max_length=500)
