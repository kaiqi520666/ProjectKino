from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.core.schemas import CamelModel
from app.modules.jobs.schemas import JobOut

CanvasNodeKind = Literal[
    "text",
    "image",
    "video",
    "audio",
    "image-generation",
    "video-generation",
]
UserAssetKind = Literal["text", "image", "video", "audio"]
UserAssetSource = Literal["canvas", "studio", "upload"]


def _validate_persisted_url(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if lowered.startswith(("blob:", "data:")):
        raise ValueError("不能保存临时 blob/data 链接，请先上传至 OSS")
    if not (lowered.startswith("https://") or lowered.startswith("http://") or cleaned.startswith("/")):
        raise ValueError("媒体链接格式不合法")
    if len(cleaned) > 4000:
        raise ValueError("媒体链接长度超过限制")
    return cleaned


class CanvasMediaPayload(CamelModel):
    url: str = Field(min_length=1, max_length=4000)
    key: str | None = Field(default=None, max_length=512)
    name: str = Field(default="", max_length=255)
    job_id: str | None = Field(default=None, max_length=64)
    model_id: str | None = Field(default=None, max_length=48)
    created_at: str | None = Field(default=None, max_length=64)

    @field_validator("url")
    @classmethod
    def check_url(cls, value: str) -> str:
        validated = _validate_persisted_url(value)
        if not validated:
            raise ValueError("媒体链接不能为空")
        return validated


class CanvasGenerationSettingsPayload(CamelModel):
    model_id: str | None = Field(default=None, max_length=48)
    ratio: str | None = Field(default=None, max_length=16)
    tier: Literal["web", "1k", "2k", "4k"] | None = None
    resolution: str | None = Field(default=None, max_length=16)
    duration_seconds: int | None = Field(default=None, ge=1, le=60)


class CanvasNodeDataPayload(CamelModel):
    title: str | None = Field(default=None, max_length=120)
    text: str | None = Field(default=None, max_length=50000)
    draft: str | None = Field(default=None, max_length=50000)
    prompt: str | None = Field(default=None, max_length=20000)
    media: CanvasMediaPayload | None = None
    history: list[CanvasMediaPayload] | None = Field(default=None, max_length=20)
    settings: CanvasGenerationSettingsPayload | None = None
    reference_order: list[str] | None = Field(default=None, max_length=64)
    last_job_id: str | None = Field(default=None, max_length=64)
    last_error: str | None = Field(default=None, max_length=1000)


class CanvasPositionPayload(CamelModel):
    x: float
    y: float


class CanvasNodePayload(CamelModel):
    id: str = Field(min_length=1, max_length=64)
    type: CanvasNodeKind
    position: CanvasPositionPayload
    data: CanvasNodeDataPayload = Field(default_factory=CanvasNodeDataPayload)


class CanvasEdgePayload(CamelModel):
    id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=64)
    target: str = Field(min_length=1, max_length=64)


class CanvasViewportPayload(CamelModel):
    x: float = 0.0
    y: float = 0.0
    zoom: float = Field(default=1.0, gt=0.05, le=20.0)


class CanvasGraphPayload(CamelModel):
    nodes: list[CanvasNodePayload] = Field(default_factory=list, max_length=200)
    edges: list[CanvasEdgePayload] = Field(default_factory=list, max_length=500)


class CanvasCreateRequest(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class CanvasUpdateRequest(CamelModel):
    expected_version: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    cover_key: str | None = Field(default=None, max_length=512)
    cover_url: str | None = Field(default=None, max_length=4000)
    viewport: CanvasViewportPayload | None = None
    graph_data: CanvasGraphPayload | None = None

    @field_validator("cover_url")
    @classmethod
    def check_cover_url(cls, value: str | None) -> str | None:
        return _validate_persisted_url(value)


class CanvasSummaryOut(CamelModel):
    id: UUID
    name: str
    description: str
    cover_url: str | None = None
    status: str
    version: int
    node_count: int
    created_at: datetime
    updated_at: datetime


class CanvasListOut(CamelModel):
    items: list[CanvasSummaryOut]


class CanvasDetailOut(CamelModel):
    id: UUID
    name: str
    description: str
    cover_key: str | None = None
    cover_url: str | None = None
    status: str
    schema_version: int
    version: int
    node_count: int
    viewport: CanvasViewportPayload | None = None
    graph_data: CanvasGraphPayload
    active_jobs: list[JobOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CanvasGenerateReference(CamelModel):
    node_id: str = Field(min_length=1, max_length=64)
    kind: UserAssetKind
    title: str = Field(default="", max_length=120)
    text: str | None = Field(default=None, max_length=20000)
    media_url: str | None = Field(default=None, max_length=4000)

    @field_validator("media_url")
    @classmethod
    def check_media_url(cls, value: str | None) -> str | None:
        return _validate_persisted_url(value)


class CanvasGenerateRequest(CamelModel):
    kind: Literal["text", "image", "video"]
    prompt: str = Field(default="", max_length=20000)
    current_text: str | None = Field(default=None, max_length=50000)
    model_id: str | None = Field(default=None, max_length=48)
    ratio: str | None = Field(default=None, max_length=16)
    tier: Literal["web", "1k", "2k", "4k"] | None = None
    resolution: str | None = Field(default=None, max_length=16)
    duration_seconds: int | None = Field(default=None, ge=1, le=60)
    references: list[CanvasGenerateReference] = Field(default_factory=list, max_length=24)


class CanvasJobAcceptedOut(CamelModel):
    canvas_id: UUID
    node_id: str
    job: JobOut


class UserAssetCreateRequest(CamelModel):
    kind: UserAssetKind
    title: str = Field(min_length=1, max_length=120)
    text_content: str | None = Field(default=None, max_length=50000)
    media_key: str | None = Field(default=None, max_length=512)
    media_url: str | None = Field(default=None, max_length=4000)
    media_name: str | None = Field(default=None, max_length=255)
    source_type: UserAssetSource = "canvas"
    source_id: UUID | None = None

    @field_validator("media_url")
    @classmethod
    def check_media_url(cls, value: str | None) -> str | None:
        return _validate_persisted_url(value)


class UserAssetOut(CamelModel):
    id: UUID
    kind: UserAssetKind
    title: str
    text_content: str | None = None
    media_key: str | None = None
    media_url: str | None = None
    media_name: str | None = None
    source_type: UserAssetSource
    source_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class UserAssetListOut(CamelModel):
    items: list[UserAssetOut]
