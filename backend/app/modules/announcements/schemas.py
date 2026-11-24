from datetime import datetime

from pydantic import Field, field_validator

from app.core.schemas import CamelModel


class AnnouncementInput(CamelModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=100000)

    @field_validator("title", "content")
    @classmethod
    def validate_nonempty(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError("标题和正文不能为空")
        return value.strip() if info.field_name == "title" else value


class AnnouncementUpdate(AnnouncementInput):
    version: int = Field(strict=True, ge=1)


class AnnouncementOut(CamelModel):
    id: int
    title: str
    content: str
    published_at: datetime


class AnnouncementIndexOut(CamelModel):
    ids: list[int]


class AnnouncementListOut(CamelModel):
    items: list[AnnouncementOut]
    has_more: bool


class AdminAnnouncementOut(AnnouncementOut):
    version: int
    updated_at: datetime


class AdminAnnouncementListOut(CamelModel):
    items: list[AdminAnnouncementOut]
    total: int
