import json
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    AuthSessionOut,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UpdateProfileRequest,
    UserOut,
)
from app.modules.credits.service import grant_credits
from app.modules.settings.service import get_registration_policy


def _session_key_from_hash(settings: Settings, token_hash: str) -> str:
    return f"{settings.redis_key_prefix}session:{token_hash}"


def _session_redis_key(settings: Settings, token: str) -> str:
    return _session_key_from_hash(settings, hash_session_token(token))


def _user_sessions_redis_key(settings: Settings, user_id: int) -> str:
    return f"{settings.redis_key_prefix}user_sessions:{user_id}"


async def issue_session(redis: Redis, settings: Settings, user: User) -> AuthSessionOut:
    token = generate_session_token()
    token_hash = hash_session_token(token)
    payload = json.dumps({"user_id": user.id, "role": user.role})
    await redis.set(
        _session_key_from_hash(settings, token_hash),
        payload,
        ex=settings.session_ttl_seconds,
    )
    user_set_key = _user_sessions_redis_key(settings, user.id)
    await redis.sadd(user_set_key, token_hash)
    await redis.expire(user_set_key, settings.session_ttl_seconds)
    return AuthSessionOut(
        access_token=token,
        expires_in=settings.session_ttl_seconds,
        user=UserOut.model_validate(user),
    )


async def revoke_session(redis: Redis, settings: Settings, token: str) -> None:
    token_hash = hash_session_token(token)
    session_key = _session_key_from_hash(settings, token_hash)
    raw = await redis.get(session_key)
    await redis.delete(session_key)
    if raw:
        try:
            user_id = int(json.loads(raw)["user_id"])
            await redis.srem(_user_sessions_redis_key(settings, user_id), token_hash)
        except (ValueError, KeyError, TypeError):
            pass


async def revoke_all_user_sessions(redis: Redis, settings: Settings, user_id: int) -> None:
    user_set_key = _user_sessions_redis_key(settings, user_id)
    members = await redis.smembers(user_set_key)
    for raw_hash in members:
        token_hash = raw_hash.decode("utf-8") if isinstance(raw_hash, bytes) else str(raw_hash)
        if token_hash:
            await redis.delete(_session_key_from_hash(settings, token_hash))
    await redis.delete(user_set_key)


async def resolve_session_user_id(redis: Redis, settings: Settings, token: str) -> int | None:
    raw = await redis.get(_session_redis_key(settings, token))
    if not raw:
        return None
    try:
        data = json.loads(raw)
        user_id = int(data["user_id"])
    except (ValueError, KeyError, TypeError):
        return None
    return user_id


async def register_user(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    body: RegisterRequest,
) -> AuthSessionOut:
    existing = await session.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        raise AppError(409, "email_exists", "该邮箱已注册，请直接登录")

    initial_credits, default_multiplier = await get_registration_policy(session)
    nickname = body.nickname.strip() or body.email.split("@", 1)[0][:40]
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        nickname=nickname,
        role="user",
        status="active",
        balance=Decimal("0.0000"),
        frozen=Decimal("0.0000"),
        usage_multiplier=default_multiplier,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise AppError(409, "email_exists", "该邮箱已注册，请直接登录") from None

    if initial_credits > 0:
        await grant_credits(
            session,
            user_id=user.id,
            amount=initial_credits,
            reason="新用户注册赠送积分",
            idempotency_key=f"registration_grant:{user.id}",
        )
    await session.commit()
    await session.refresh(user)
    return await issue_session(redis, settings, user)


async def login_user(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    body: LoginRequest,
) -> AuthSessionOut:
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise AppError(401, "invalid_credentials", "邮箱或密码错误")
    if user.status != "active":
        raise AppError(403, "user_disabled", "该账号已被禁用")
    return await issue_session(redis, settings, user)


async def update_user_profile(
    session: AsyncSession,
    *,
    user: User,
    body: UpdateProfileRequest,
) -> UserOut:
    user.nickname = body.nickname
    await session.commit()
    await session.refresh(user)
    return UserOut.model_validate(user)


async def change_user_password(
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    *,
    user: User,
    current_token: str,
    body: ChangePasswordRequest,
) -> AuthSessionOut:
    if not verify_password(body.current_password, user.password_hash):
        raise AppError(400, "invalid_current_password", "当前密码不正确")
    if body.new_password == body.current_password:
        raise AppError(400, "password_unchanged", "新密码不能与当前密码相同")

    user.password_hash = hash_password(body.new_password)
    await session.commit()
    await session.refresh(user)

    # 失效该用户的全部旧会话（含多端与历史未索引会话），并签发新会话避免当前端掉线。
    await revoke_all_user_sessions(redis, settings, user.id)
    await revoke_session(redis, settings, current_token)
    return await issue_session(redis, settings, user)
