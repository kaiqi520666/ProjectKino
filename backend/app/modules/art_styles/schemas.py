import re
from datetime import datetime

from pydantic import Field, field_validator

from app.core.schemas import CamelModel

_CODE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _validate_http_url(value: str) -> str:
    cleaned = value.strip()
    if not cleaned.startswith(("http://", "https://")):
        raise ValueError("图片链接必须为有效的 http/https 地址")
    return cleaned


class ArtStyleOut(CamelModel):
    id: int
    code: str
    label: str
    prompt: str
    image_url: str
    is_enabled: bool
    is_default: bool
    sort_order: int


class ArtStyleListOut(CamelModel):
    items: list[ArtStyleOut]


class AdminArtStyleOut(ArtStyleOut):
    image_key: str
    project_count: int = 0
    created_at: datetime
    updated_at: datetime


class AdminArtStyleListOut(CamelModel):
    items: list[AdminArtStyleOut]
    total: int


class ArtStyleUploadPolicyRequest(CamelModel):
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=3, max_length=120)
    size: int = Field(gt=0, le=5 * 1024 * 1024)
    code: str | None = Field(default=None, max_length=64)


class ArtStyleCreateRequest(CamelModel):
    code: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=64)
    prompt: str = Field(min_length=1, max_length=1000)
    image_key: str = Field(min_length=1, max_length=512)
    image_url: str = Field(min_length=1, max_length=2048)
    is_enabled: bool = True
    is_default: bool = False
    sort_order: int = Field(default=100, ge=0, le=99999)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not _CODE_RE.match(cleaned):
            raise ValueError("标识仅支持小写字母、数字和连字符（如 ink-painting）")
        return cleaned

    @field_validator("label", "prompt", "image_key")
    @classmethod
    def validate_nonempty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("字段不能为空")
        return cleaned

    @field_validator("image_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _validate_http_url(value)


class ArtStyleUpdateRequest(CamelModel):
    label: str | None = Field(default=None, min_length=1, max_length=64)
    prompt: str | None = Field(default=None, min_length=1, max_length=1000)
    image_key: str | None = Field(default=None, min_length=1, max_length=512)
    image_url: str | None = Field(default=None, min_length=1, max_length=2048)
    is_enabled: bool | None = None
    is_default: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=99999)

    @field_validator("label", "prompt", "image_key")
    @classmethod
    def validate_optional_nonempty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("字段不能为空")
        return cleaned

    @field_validator("image_url")
    @classmethod
    def validate_optional_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_http_url(value)
