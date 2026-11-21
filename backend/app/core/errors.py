from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def register_errors(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        body: dict[str, Any] = {
            "code": exc.code,
            "message": exc.message,
            "detail": exc.message,
            "data": exc.details,
        }
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else None
        msg = "请求参数校验失败"
        if first:
            loc = ".".join(str(part) for part in first.get("loc", []) if part != "body")
            err = first.get("msg", "")
            msg = f"参数 {loc} 无效：{err}" if loc else f"参数无效：{err}"
        return JSONResponse(
            status_code=422,
            content={"code": "validation_error", "message": msg, "detail": msg, "data": None},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        msg = exc.detail if isinstance(exc.detail, str) else "请求失败"
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": f"http_{exc.status_code}", "message": msg, "detail": msg, "data": None},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", exception_type=type(exc).__name__)
        msg = "服务内部错误，请稍后重试"
        return JSONResponse(
            status_code=500,
            content={"code": "internal_error", "message": msg, "detail": msg, "data": None},
        )
