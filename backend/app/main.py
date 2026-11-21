from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.credits import router as credits_router
from app.api.v1.health import router as health_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.models import router as models_router
from app.api.v1.projects import router as projects_router
from app.api.v1.uploads import router as uploads_router
from app.core.config import Settings
from app.core.errors import register_errors
from app.core.logging import configure_logging
from app.core.request_context import RequestContextMiddleware
from app.db.session import create_engine, dispose_engine
from app.workers.broker import ai_broker, media_broker


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()
    configure_logging(cfg.log_level)
    logger = structlog.get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_engine(cfg)
        redis = Redis.from_url(
            cfg.redis_url.get_secret_value(),
            decode_responses=True,
            socket_connect_timeout=cfg.dependency_timeout_seconds,
            socket_timeout=None,
            socket_keepalive=True,
        )
        http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=False)
        if cfg.environment != "test":
            await ai_broker.startup()
            await media_broker.startup()
        try:
            app.state.settings = cfg
            app.state.engine = engine
            app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)
            app.state.redis = redis
            app.state.http = http_client
            logger.info("application_started", environment=cfg.environment)
            yield
        finally:
            if cfg.environment != "test":
                await media_broker.shutdown()
                await ai_broker.shutdown()
            await http_client.aclose()
            await redis.aclose()
            await dispose_engine(engine)
            logger.info("application_stopped")

    app = FastAPI(
        title="FrameDrama API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if cfg.environment != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if cfg.environment != "production" else None,
    )
    register_errors(app)
    app.add_middleware(RequestContextMiddleware)
    if cfg.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-Request-ID",
                "X-Trace-ID",
                "Idempotency-Key",
            ],
            expose_headers=["X-Request-ID", "X-Trace-ID"],
        )

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(credits_router, prefix="/api/v1")
    app.include_router(models_router, prefix="/api/v1")
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(uploads_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    return app
