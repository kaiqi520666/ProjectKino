from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import ApiResponse
from app.db.session import get_session
from app.modules.announcements import service
from app.modules.announcements.schemas import (
    AdminAnnouncementListOut,
    AdminAnnouncementOut,
    AnnouncementIndexOut,
    AnnouncementInput,
    AnnouncementListOut,
    AnnouncementOut,
    AnnouncementUpdate,
)
from app.modules.auth.deps import get_current_user, require_admin
from app.modules.auth.models import User

router = APIRouter(prefix="/announcements", tags=["announcements"])
admin_router = APIRouter(
    prefix="/admin/announcements",
    tags=["admin-announcements"],
    dependencies=[Depends(require_admin)],
)


@router.get("/index", response_model=ApiResponse[AnnouncementIndexOut])
async def get_announcements_index(
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AnnouncementIndexOut]:
    ids = await service.get_announcement_index(session)
    return ApiResponse(data=AnnouncementIndexOut(ids=ids))


@router.get("", response_model=ApiResponse[AnnouncementListOut])
async def list_announcements(
    before_id: Annotated[int | None, Query(alias="beforeId", ge=1)] = None,
    limit: int = Query(default=20, ge=1, le=50),
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AnnouncementListOut]:
    rows, has_more = await service.list_announcements(
        session, before_id=before_id, limit=limit
    )
    return ApiResponse(
        data=AnnouncementListOut(
            items=[AnnouncementOut.model_validate(row) for row in rows],
            has_more=has_more,
        )
    )


@admin_router.get("", response_model=ApiResponse[AdminAnnouncementListOut])
async def admin_list_announcements(
    keyword: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminAnnouncementListOut]:
    rows, total = await service.list_admin_announcements(
        session, keyword=keyword, limit=limit, offset=offset
    )
    return ApiResponse(
        data=AdminAnnouncementListOut(
            items=[AdminAnnouncementOut.model_validate(row) for row in rows],
            total=total,
        )
    )


@admin_router.post("", response_model=ApiResponse[AdminAnnouncementOut], status_code=201)
async def admin_create_announcement(
    body: AnnouncementInput,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminAnnouncementOut]:
    row = await service.create_announcement(
        session,
        title=body.title,
        content=body.content,
        created_by=admin.id,
    )
    await session.commit()
    await session.refresh(row)
    return ApiResponse(data=AdminAnnouncementOut.model_validate(row))


@admin_router.patch("/{announcement_id}", response_model=ApiResponse[AdminAnnouncementOut])
async def admin_update_announcement(
    announcement_id: Annotated[int, Path(ge=1)],
    body: AnnouncementUpdate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminAnnouncementOut]:
    row = await service.update_announcement(
        session,
        announcement_id=announcement_id,
        title=body.title,
        content=body.content,
        version=body.version,
    )
    await session.commit()
    await session.refresh(row)
    return ApiResponse(data=AdminAnnouncementOut.model_validate(row))


@admin_router.delete("/{announcement_id}", response_model=ApiResponse[dict])
async def admin_delete_announcement(
    announcement_id: Annotated[int, Path(ge=1)],
    version: Annotated[int, Query(ge=1)],
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    await service.delete_announcement(
        session, announcement_id=announcement_id, version=version
    )
    await session.commit()
    return ApiResponse(data={"id": announcement_id, "deleted": True})
