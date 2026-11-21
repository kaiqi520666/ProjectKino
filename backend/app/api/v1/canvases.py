from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import ApiResponse
from app.db.session import get_session
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.canvas.schemas import (
    CanvasCreateRequest,
    CanvasDetailOut,
    CanvasListOut,
    CanvasUpdateRequest,
    UserAssetCreateRequest,
    UserAssetListOut,
    UserAssetOut,
)
from app.modules.canvas.service import (
    archive_canvas,
    create_canvas,
    create_user_asset,
    delete_user_asset,
    get_user_canvas,
    list_canvas_active_jobs,
    list_user_assets,
    list_user_canvases,
    serialize_canvas_detail,
    serialize_canvas_summary,
    update_canvas,
)

router = APIRouter(prefix="/canvases", tags=["canvases"])
assets_router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=ApiResponse[CanvasListOut])
async def list_canvases(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CanvasListOut]:
    canvases = await list_user_canvases(session, user_id=user.id)
    return ApiResponse(data=CanvasListOut(items=[serialize_canvas_summary(c) for c in canvases]))


@router.post("", response_model=ApiResponse[CanvasDetailOut], status_code=201)
async def create_canvas_endpoint(
    body: CanvasCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CanvasDetailOut]:
    canvas = await create_canvas(session, user_id=user.id, body=body)
    await session.commit()
    await session.refresh(canvas)
    return ApiResponse(data=serialize_canvas_detail(canvas, []))


@router.get("/{canvas_id}", response_model=ApiResponse[CanvasDetailOut])
async def get_canvas_endpoint(
    canvas_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CanvasDetailOut]:
    canvas = await get_user_canvas(session, canvas_id=canvas_id, user_id=user.id)
    active_jobs = await list_canvas_active_jobs(session, canvas_id=canvas.id, user_id=user.id)
    return ApiResponse(data=serialize_canvas_detail(canvas, active_jobs))


@router.patch("/{canvas_id}", response_model=ApiResponse[CanvasDetailOut])
async def update_canvas_endpoint(
    canvas_id: UUID,
    body: CanvasUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CanvasDetailOut]:
    canvas = await update_canvas(session, canvas_id=canvas_id, user_id=user.id, body=body)
    await session.commit()
    await session.refresh(canvas)
    active_jobs = await list_canvas_active_jobs(session, canvas_id=canvas.id, user_id=user.id)
    return ApiResponse(data=serialize_canvas_detail(canvas, active_jobs))


@router.delete("/{canvas_id}", response_model=ApiResponse[dict])
async def delete_canvas_endpoint(
    canvas_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    await archive_canvas(session, canvas_id=canvas_id, user_id=user.id)
    await session.commit()
    return ApiResponse(data={"id": str(canvas_id), "archived": True})


@assets_router.get("", response_model=ApiResponse[UserAssetListOut])
async def list_assets_endpoint(
    kind: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[UserAssetListOut]:
    assets = await list_user_assets(session, user_id=user.id, kind=kind)
    return ApiResponse(data=UserAssetListOut(items=[UserAssetOut.model_validate(a) for a in assets]))


@assets_router.post("", response_model=ApiResponse[UserAssetOut], status_code=201)
async def create_asset_endpoint(
    body: UserAssetCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[UserAssetOut]:
    asset = await create_user_asset(session, user_id=user.id, body=body)
    await session.commit()
    await session.refresh(asset)
    return ApiResponse(data=UserAssetOut.model_validate(asset))


@assets_router.delete("/{asset_id}", response_model=ApiResponse[dict])
async def delete_asset_endpoint(
    asset_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    await delete_user_asset(session, asset_id=asset_id, user_id=user.id)
    await session.commit()
    return ApiResponse(data={"id": str(asset_id), "deleted": True})
