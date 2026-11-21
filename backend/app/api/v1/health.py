import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def health_live() -> dict:
    return {"code": "ok", "message": "ok", "data": {"status": "alive"}}


@router.get("/ready")
async def health_ready(request: Request):
    timeout = request.app.state.settings.dependency_timeout_seconds
    checks = {"postgres": False, "redis": False}

    try:
        async with asyncio.timeout(timeout):
            async with request.app.state.sessions() as session:
                await session.execute(text("SELECT 1"))
            checks["postgres"] = True
    except Exception:
        checks["postgres"] = False

    try:
        async with asyncio.timeout(timeout):
            pong = await request.app.state.redis.ping()
            checks["redis"] = bool(pong)
    except Exception:
        checks["redis"] = False

    ok = all(checks.values())
    status_code = 200 if ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "code": "ok" if ok else "dependency_unavailable",
            "message": "ok" if ok else "依赖服务不可用",
            "data": checks,
        },
    )
