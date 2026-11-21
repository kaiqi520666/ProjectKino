from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_session
from app.modules.auth.models import User
from app.modules.auth.service import resolve_session_user_id


def extract_bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise AppError(401, "unauthorized", "请先登录")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise AppError(401, "unauthorized", "无效的登录凭证")
    return parts[1].strip()


async def get_current_user(
    request: Request,
    token: str = Depends(extract_bearer_token),
    session: AsyncSession = Depends(get_session),
) -> User:
    user_id = await resolve_session_user_id(request.app.state.redis, request.app.state.settings, token)
    if user_id is None:
        raise AppError(401, "session_expired", "登录已过期，请重新登录")
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None or user.status != "active":
        raise AppError(401, "unauthorized", "账号不可用，请重新登录")
    return user


def require_roles(*allowed_roles: str):
    allowed = set(allowed_roles)

    async def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise AppError(403, "forbidden", "权限不足，无法访问该后台接口")
        return user

    return _dependency


require_admin = require_roles("admin")
require_staff = require_roles("admin", "operator")
