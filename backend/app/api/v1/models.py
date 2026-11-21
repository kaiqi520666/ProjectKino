from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import ApiResponse
from app.db.session import get_session
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.catalog.schemas import ModelCatalogOut
from app.modules.catalog.service import list_enabled_catalog

router = APIRouter(tags=["models"])


@router.get("/models", response_model=ApiResponse[ModelCatalogOut])
async def get_models(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ModelCatalogOut]:
    catalog = await list_enabled_catalog(session, usage_multiplier=user.usage_multiplier)
    return ApiResponse(data=catalog)
