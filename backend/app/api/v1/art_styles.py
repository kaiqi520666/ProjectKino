from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.uploads import OssUploadPolicyOut
from app.core.errors import AppError
from app.core.schemas import ApiResponse
from app.db.session import get_session
from app.modules.art_styles import service
from app.modules.art_styles.schemas import (
    AdminArtStyleListOut,
    AdminArtStyleOut,
    ArtStyleCreateRequest,
    ArtStyleListOut,
    ArtStyleUpdateRequest,
    ArtStyleUploadPolicyRequest,
)
from app.modules.auth.deps import get_current_user, require_admin
from app.modules.auth.models import User
from app.modules.storage.oss import load_storage, try_load_storage

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/art-styles", tags=["art-styles"])
admin_router = APIRouter(
    prefix="/admin/art-styles",
    tags=["admin-art-styles"],
    dependencies=[Depends(require_admin)],
)


async def _cleanup_old_oss_key(session: AsyncSession, key: str | None) -> None:
    if not key:
        return
    storage = await try_load_storage(session)
    if storage is None:
        return
    required_prefix = f"{storage.config.prefix}/system/{service.SYSTEM_ART_STYLES_CATEGORY}/"
    if not key.startswith(required_prefix):
        return
    try:
        storage.delete_objects([key], required_prefix=required_prefix)
    except Exception:
        logger.warning("art_style_oss_cleanup_failed", key=key)


@router.get("", response_model=ApiResponse[ArtStyleListOut])
async def list_art_styles(
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ArtStyleListOut]:
    rows = await service.list_public_art_styles(session)
    storage = await try_load_storage(session)
    return ApiResponse(
        data=ArtStyleListOut(
            items=[service.serialize_art_style(row, storage) for row in rows],
        )
    )


@admin_router.get("", response_model=ApiResponse[AdminArtStyleListOut])
async def admin_list_art_styles(
    keyword: str | None = Query(default=None, max_length=100),
    status: Literal["all", "enabled", "disabled"] = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminArtStyleListOut]:
    rows, total, usage_counts = await service.list_admin_art_styles(
        session,
        keyword=keyword,
        status=status,
        limit=limit,
        offset=offset,
    )
    storage = await try_load_storage(session)
    return ApiResponse(
        data=AdminArtStyleListOut(
            items=[
                service.serialize_admin_art_style(
                    row,
                    storage,
                    project_count=usage_counts.get(row.code, 0),
                )
                for row in rows
            ],
            total=total,
        )
    )


@admin_router.post("/upload-policy", response_model=ApiResponse[OssUploadPolicyOut])
async def admin_art_style_upload_policy(
    body: ArtStyleUploadPolicyRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[OssUploadPolicyOut]:
    if not body.mime_type.lower().startswith("image/"):
        raise AppError(400, "invalid_mime_type", "画风封面仅支持图片格式")
    storage = await load_storage(session)
    policy = storage.system_upload_policy(
        category=service.SYSTEM_ART_STYLES_CATEGORY,
        file_name=body.file_name,
        mime_type=body.mime_type,
        size=body.size,
        slug=body.code,
    )
    return ApiResponse(data=OssUploadPolicyOut.model_validate(policy))


@admin_router.post("", response_model=ApiResponse[AdminArtStyleOut], status_code=201)
async def admin_create_art_style(
    body: ArtStyleCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminArtStyleOut]:
    row = await service.create_art_style(session, body)
    await session.commit()
    await session.refresh(row)
    storage = await try_load_storage(session)
    return ApiResponse(data=service.serialize_admin_art_style(row, storage))


@admin_router.patch("/{style_id}", response_model=ApiResponse[AdminArtStyleOut])
async def admin_update_art_style(
    style_id: Annotated[int, Path(ge=1)],
    body: ArtStyleUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AdminArtStyleOut]:
    row, old_key = await service.update_art_style(session, style_id=style_id, body=body)
    await session.commit()
    await session.refresh(row)
    await _cleanup_old_oss_key(session, old_key)
    storage = await try_load_storage(session)
    usage = await service.get_project_usage_counts(session, [row.code])
    return ApiResponse(
        data=service.serialize_admin_art_style(
            row,
            storage,
            project_count=usage.get(row.code, 0),
        )
    )


@admin_router.delete("/{style_id}", response_model=ApiResponse[dict])
async def admin_delete_art_style(
    style_id: Annotated[int, Path(ge=1)],
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    image_key = await service.delete_art_style(session, style_id=style_id)
    await session.commit()
    await _cleanup_old_oss_key(session, image_key)
    return ApiResponse(data={"id": style_id, "deleted": True})
