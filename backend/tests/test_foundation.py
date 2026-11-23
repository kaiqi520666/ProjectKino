from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.core.security import hash_password, verify_password
from app.main import create_app


class FakeRedis:
    def __init__(self, *, healthy: bool = True) -> None:
        self.healthy = healthy
        self.store: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}

    async def ping(self) -> bool:
        if not self.healthy:
            raise ConnectionError("redis down")
        return True

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def delete(self, key: str) -> int:
        removed_val = self.store.pop(key, None) is not None
        removed_set = self.sets.pop(key, None) is not None
        return 1 if (removed_val or removed_set) else 0

    async def sadd(self, key: str, *values: str) -> int:
        bucket = self.sets.setdefault(key, set())
        before = len(bucket)
        bucket.update(values)
        return len(bucket) - before

    async def srem(self, key: str, *values: str) -> int:
        bucket = self.sets.get(key)
        if not bucket:
            return 0
        before = len(bucket)
        for value in values:
            bucket.discard(value)
        return before - len(bucket)

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    async def expire(self, key: str, seconds: int) -> bool:
        return key in self.store or key in self.sets

    async def aclose(self) -> None:
        return None


class FakeSession:
    def __init__(self, *, healthy: bool = True) -> None:
        self.healthy = healthy

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def execute(self, stmt):
        if not self.healthy:
            raise ConnectionError("pg down")
        return SimpleNamespace(scalar=lambda: 1)


def _test_app(*, pg_ok: bool = True, redis_ok: bool = True):
    app = create_app(Settings(environment="test"))
    app.state.settings = Settings(environment="test")
    app.state.sessions = lambda: FakeSession(healthy=pg_ok)
    app.state.redis = FakeRedis(healthy=redis_ok)
    return app


def test_password_scrypt_roundtrip():
    hashed = hash_password("Secret123!")
    assert hashed.startswith("scrypt:")
    assert verify_password("Secret123!", hashed) is True
    assert verify_password("WrongPass!", hashed) is False
    assert verify_password("Secret123!", "invalid-format") is False


async def test_health_live_and_request_headers():
    app = _test_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health/live", headers={"X-Request-ID": "req-123"})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "alive"
    assert resp.headers["X-Request-ID"] == "req-123"
    assert resp.headers["X-Trace-ID"] == "req-123"


async def test_health_ready_reports_dependency_status():
    app_ok = _test_app(pg_ok=True, redis_ok=True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_ok), base_url="http://test") as client:
        resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json()["data"] == {"postgres": True, "redis": True}

    app_bad = _test_app(pg_ok=True, redis_ok=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_bad), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 503
    assert resp.json()["data"] == {"postgres": True, "redis": False}


async def test_protected_endpoint_requires_bearer_token():
    app = _test_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"
    assert text("SELECT 1") is not None


@pytest.mark.asyncio
async def test_session_issue_resolve_and_revoke():
    from decimal import Decimal

    from app.modules.auth.models import User
    from app.modules.auth.service import issue_session, resolve_session_user_id, revoke_session

    redis = FakeRedis()
    settings = Settings(environment="test")
    user = User(
        id=42,
        email="founder@framedrama.ai",
        password_hash=hash_password("Pass1234"),
        nickname="创始人",
        role="user",
        status="active",
        balance=Decimal("100.0000"),
        frozen=Decimal("0.0000"),
        usage_multiplier=Decimal("1.0000"),
    )
    issued = await issue_session(redis, settings, user)
    assert issued.user.email == "founder@framedrama.ai"
    assert await resolve_session_user_id(redis, settings, issued.access_token) == 42

    await revoke_session(redis, settings, issued.access_token)
    assert await resolve_session_user_id(redis, settings, issued.access_token) is None


@pytest.mark.asyncio
async def test_update_profile_and_change_password_revokes_all_old_sessions():
    from decimal import Decimal

    from app.core.errors import AppError
    from app.modules.auth.models import User
    from app.modules.auth.schemas import ChangePasswordRequest, UpdateProfileRequest
    from app.modules.auth.service import (
        change_user_password,
        issue_session,
        resolve_session_user_id,
        update_user_profile,
    )

    class _DummySession:
        async def commit(self) -> None:
            return None

        async def refresh(self, obj) -> None:
            return None

    redis = FakeRedis()
    settings = Settings(environment="test")
    user = User(
        id=99,
        email="creator@framedrama.ai",
        password_hash=hash_password("OldPass123"),
        nickname="原昵称",
        role="user",
        status="active",
        balance=Decimal("50.0000"),
        frozen=Decimal("0.0000"),
        usage_multiplier=Decimal("1.0000"),
    )
    db = _DummySession()

    updated = await update_user_profile(
        db,  # type: ignore[arg-type]
        user=user,
        body=UpdateProfileRequest(nickname="  新导演  "),
    )
    assert updated.nickname == "新导演"

    # 模拟两个设备同时在线
    sess_a = await issue_session(redis, settings, user)
    sess_b = await issue_session(redis, settings, user)
    assert await resolve_session_user_id(redis, settings, sess_a.access_token) == 99
    assert await resolve_session_user_id(redis, settings, sess_b.access_token) == 99

    # 旧密码错误应拒絶
    with pytest.raises(AppError) as wrong_err:
        await change_user_password(
            db,  # type: ignore[arg-type]
            redis,  # type: ignore[arg-type]
            settings,
            user=user,
            current_token=sess_a.access_token,
            body=ChangePasswordRequest(current_password="Wrong!", new_password="NewPass456"),
        )
    assert wrong_err.value.code == "invalid_current_password"

    # 新旧密码相同应拒绝
    with pytest.raises(AppError) as same_err:
        await change_user_password(
            db,  # type: ignore[arg-type]
            redis,  # type: ignore[arg-type]
            settings,
            user=user,
            current_token=sess_a.access_token,
            body=ChangePasswordRequest(current_password="OldPass123", new_password="OldPass123"),
        )
    assert same_err.value.code == "password_unchanged"

    # 正常改密：旧密码失效、双端旧会话全部吊销、返回的新会话立即生效
    refreshed = await change_user_password(
        db,  # type: ignore[arg-type]
        redis,  # type: ignore[arg-type]
        settings,
        user=user,
        current_token=sess_a.access_token,
        body=ChangePasswordRequest(current_password="OldPass123", new_password="NewPass456"),
    )
    assert verify_password("NewPass456", user.password_hash) is True
    assert verify_password("OldPass123", user.password_hash) is False
    assert await resolve_session_user_id(redis, settings, sess_a.access_token) is None
    assert await resolve_session_user_id(redis, settings, sess_b.access_token) is None
    assert refreshed.access_token not in {sess_a.access_token, sess_b.access_token}
    assert await resolve_session_user_id(redis, settings, refreshed.access_token) == 99
