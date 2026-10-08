"""Global exception handlers producing the standard error envelope."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from resume_matching.core.errors import AppError
from resume_matching.core.logging import request_id_var

logger = logging.getLogger(__name__)


def error_response(
    status: int,
    message: str,
    errors: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "success": False,
            "message": message,
            "errors": errors or [],
            "traceId": request_id_var.get(),
        },
        headers=headers,
    )


def _field(loc: tuple) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "header")]
    return ".".join(parts) or "request"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("app_error", extra={"error": type(exc).__name__, "detail": exc.message})
        return error_response(
            exc.status_code,
            exc.message,
            [{"field": e.field, "message": e.message} for e in exc.errors],
            exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"field": _field(tuple(e["loc"])), "message": e["msg"]} for e in exc.errors()]
        return error_response(422, "Validation failed", errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return error_response(exc.status_code, message, headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", extra={"error": type(exc).__name__})
        return error_response(500, "Internal server error")
