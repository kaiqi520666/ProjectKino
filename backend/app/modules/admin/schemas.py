from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.core.schemas import CamelModel
from app.modules.credits.schemas import CreditLedgerOut


class AdminProviderHealthOut(CamelModel):
    key: str
    display_name: str
    adapter: str
    base_url: str
    enabled: bool
    has_api_key: bool


class AdminOverviewOut(CamelModel):
    total_users: int
    active_users: int
    operator_count: int
    admin_count: int
    active_projects: int
    archived_projects: int
    running_jobs: int
    review_jobs: int
    failed_jobs_24h: int
    total_balance: Decimal
    total_frozen: Decimal
    oss_configured: bool
    providers: list[AdminProviderHealthOut]


class AdminUserItemOut(CamelModel):
    id: int
    email: str
    nickname: str
    role: Literal["user", "operator", "admin"]
    status: Literal["active", "disabled"]
    balance: Decimal
    frozen: Decimal
    usage_multiplier: Decimal
    project_count: int
    job_count: int
    created_at: datetime


class AdminUserListOut(CamelModel):
    items: list[AdminUserItemOut]
    total: int


class AdminUserUpdateRequest(CamelModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=80)
    role: Literal["user", "operator", "admin"] | None = None
    status: Literal["active", "disabled"] | None = None
    usage_multiplier: Decimal | None = Field(default=None, gt=Decimal("0"), le=Decimal("100"))


class AdminUserLedgersOut(CamelModel):
    user: AdminUserItemOut
    items: list[CreditLedgerOut]
    total: int


class AdminJobItemOut(CamelModel):
    id: UUID
    user_id: int
    user_email: str
    user_nickname: str = ""
    project_id: UUID | None = None
    project_name: str | None = None
    canvas_id: UUID | None = None
    canvas_name: str | None = None
    job_type: str
    target_id: str | None = None
    status: str
    step_index: int
    step_total: int
    step_label: str
    progress: int
    provider_task_id: str | None = None
    input_payload: dict[str, Any]
    result_payload: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    usage_summary: dict[str, Any] | None = None
    reservation_id: UUID | None = None
    reservation_amount: Decimal | None = None
    reservation_status: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AdminJobListOut(CamelModel):
    items: list[AdminJobItemOut]
    total: int
    review_count: int


class AdminJobRefundRequest(CamelModel):
    reason: str = Field(default="管理员核实上游未扣费，退还冻结积分", min_length=1, max_length=200)


class AdminJobRescueMediaRequest(CamelModel):
    media_url: str = Field(min_length=8, max_length=4000)
    note: str = Field(default="管理员人工补录上游成片并结算", max_length=200)


class AdminProviderOut(CamelModel):
    id: int
    key: str
    display_name: str
    base_url: str
    adapter: str
    auth_type: str
    auth_header: str | None = None
    enabled: bool
    has_api_key: bool
    configuration: dict[str, Any] = Field(default_factory=dict)


class AdminTextPriceInOut(CamelModel):
    input_price_per_million: Decimal = Field(ge=Decimal("0"))
    cached_input_price_per_million: Decimal = Field(ge=Decimal("0"))
    output_price_per_million: Decimal = Field(ge=Decimal("0"))


class AdminImagePriceInOut(CamelModel):
    tier: Literal["web", "1k", "2k", "4k"]
    credit_price: Decimal = Field(ge=Decimal("0"))


class AdminVideoPriceInOut(CamelModel):
    rule_key: str = Field(min_length=1, max_length=64)
    unit: Literal["second", "call"] = "second"
    credit_price: Decimal = Field(ge=Decimal("0"))


class AdminModelItemOut(CamelModel):
    id: str
    provider_id: int
    provider_key: str
    provider_name: str
    media_type: Literal["text", "image", "video"]
    category: str = ""
    display_name: str
    upstream_model_id: str
    enabled: bool
    upstream_available: bool = True
    last_synced_at: datetime | None = None
    is_default: bool
    sort: int
    capabilities: dict[str, Any] = Field(default_factory=dict)
    defaults: dict[str, Any] = Field(default_factory=dict)
    configuration: dict[str, Any] = Field(default_factory=dict)
    text_price: AdminTextPriceInOut | None = None
    image_prices: list[AdminImagePriceInOut] = Field(default_factory=list)
    video_prices: list[AdminVideoPriceInOut] = Field(default_factory=list)


class AdminModelCreateRequest(CamelModel):
    id: str = Field(min_length=2, max_length=48, pattern=r"^[a-zA-Z0-9._-]+$")
    provider_key: str = Field(default="cc", min_length=1, max_length=32)
    media_type: Literal["text", "image", "video"] = "video"
    category: str = Field(default="", max_length=48)
    display_name: str = Field(min_length=1, max_length=80)
    upstream_model_id: str = Field(min_length=1, max_length=200)
    enabled: bool = True
    is_default: bool = False
    sort: int = 100
    capabilities: dict[str, Any] = Field(default_factory=dict)
    defaults: dict[str, Any] = Field(default_factory=dict)
    configuration: dict[str, Any] = Field(default_factory=dict)
    text_price: AdminTextPriceInOut | None = None
    image_prices: list[AdminImagePriceInOut] | None = None
    video_prices: list[AdminVideoPriceInOut] | None = None


class AdminModelUpdateRequest(CamelModel):
    category: str | None = Field(default=None, max_length=48)
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    upstream_model_id: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    is_default: bool | None = None
    sort: int | None = None
    capabilities: dict[str, Any] | None = None
    defaults: dict[str, Any] | None = None
    configuration: dict[str, Any] | None = None
    text_price: AdminTextPriceInOut | None = None
    image_prices: list[AdminImagePriceInOut] | None = None
    video_prices: list[AdminVideoPriceInOut] | None = None


class AdminModelSyncLogOut(CamelModel):
    id: int
    provider_key: str
    model_id: str
    upstream_model_id: str
    event_type: Literal["offline", "restored"]
    summary: str
    created_at: datetime


class AdminModelSyncLogListOut(CamelModel):
    items: list[AdminModelSyncLogOut]
    total: int


class AdminModelReorderRequest(CamelModel):
    model_ids: list[str] = Field(min_length=2, max_length=200)


class AdminOssSettingsOut(CamelModel):
    endpoint: str
    bucket: str
    public_base_url: str
    prefix: str
    timeout_seconds: int
    has_credentials: bool
    configured: bool


class AdminRegistrationSettingsOut(CamelModel):
    initial_credits: Decimal
    default_usage_multiplier: Decimal


class AdminRegistrationSettingsUpdate(CamelModel):
    initial_credits: Decimal = Field(ge=Decimal("0"), le=Decimal("1000000"))
    default_usage_multiplier: Decimal = Field(gt=Decimal("0"), le=Decimal("100"))


class AdminSettingsOut(CamelModel):
    oss: AdminOssSettingsOut
    registration: AdminRegistrationSettingsOut


class AdminProjectItemOut(CamelModel):
    id: UUID
    user_id: int
    user_email: str
    name: str
    status: str
    episode_count: int
    asset_count: int
    clip_count: int
    job_count: int
    active_job_count: int
    created_at: datetime
    updated_at: datetime


class AdminProjectListOut(CamelModel):
    items: list[AdminProjectItemOut]
    total: int
    archived_count: int

