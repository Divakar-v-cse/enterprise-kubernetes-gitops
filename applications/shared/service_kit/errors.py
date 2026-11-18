"""Uniform API error envelope and request correlation middleware."""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logging import get_logger, request_id_var

logger = get_logger("service.error")


class ApiError(Exception):
    """Domain error rendered as a stable JSON envelope."""

    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def _envelope(code: str, message: str, request_id: str, details: dict | None = None) -> dict:
    body = {"error": {"code": code, "message": message, "request_id": request_id}}
    if details:
        body["error"]["details"] = details
    return body


def install_error_handlers(app: FastAPI, service: str) -> None:
    @app.middleware("http")
    async def _request_context(request: Request, call_next):
        incoming = request.headers.get("x-request-id") or str(uuid.uuid4())
        token = request_id_var.set(incoming[:64])
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "unhandled_exception",
                extra={"service": service, "method": request.method, "path": request.url.path},
            )
            raise
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = incoming
        response.headers["x-response-time-ms"] = f"{(time.perf_counter() - started) * 1000:.2f}"
        logger.info(
            "request",
            extra={
                "service": service,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        request_id = request.headers.get("x-request-id", "-")
        log = logger.warning if exc.status_code < 500 else logger.error
        log(
            "api_error",
            extra={"code": exc.code, "status": exc.status_code, "path": request.url.path},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, request_id, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        request_id = request.headers.get("x-request-id", "-")
        return JSONResponse(
            status_code=422,
            content=_envelope(
                "validation_error",
                "Request validation failed",
                request_id,
                {"errors": exc.errors()},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        request_id = request.headers.get("x-request-id", "-")
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(
                f"http_{exc.status_code}", str(exc.detail), request_id
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        request_id = request.headers.get("x-request-id", "-")
        logger.exception("unhandled_error", extra={"path": request.url.path})
        return JSONResponse(
            status_code=500,
            content=_envelope("internal_error", "Unexpected server error", request_id),
        )
