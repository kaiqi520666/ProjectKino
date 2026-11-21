from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import ApiResponse
from app.db.session import get_session
from app.modules.auth.deps import extract_bearer_token, get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import AuthSessionOut, LoginRequest, RegisterRequest, UserOut
from app.modules.auth.service import login_user, register_user, revoke_session

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=ApiResponse[AuthSessionOut], status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AuthSessionOut]:
    result = await register_user(session, request.app.state.redis, request.app.state.settings, body)
    return ApiResponse(data=result)


@router.post("/auth/login", response_model=ApiResponse[AuthSessionOut])
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AuthSessionOut]:
    result = await login_user(session, request.app.state.redis, request.app.state.settings, body)
    return ApiResponse(data=result)


@router.post("/auth/logout", response_model=ApiResponse[dict])
async def logout(
    request: Request,
    token: str = Depends(extract_bearer_token),
) -> ApiResponse[dict]:
    await revoke_session(request.app.state.redis, request.app.state.settings, token)
    return ApiResponse(data={"loggedOut": True})


@router.get("/users/me", response_model=ApiResponse[UserOut])
async def me(user: User = Depends(get_current_user)) -> ApiResponse[UserOut]:
    return ApiResponse(data=UserOut.model_validate(user))
