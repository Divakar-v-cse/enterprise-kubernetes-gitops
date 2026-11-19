"""FastAPI application factory with probes, metrics and lifespan wiring."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import BaseSettings
from .errors import install_error_handlers
from .logging import configure_logging, get_logger
from .metrics import SERVICE_UP, install_metrics

logger = get_logger("service.app")


def build_app(
    settings: BaseSettings,
    *,
    title: str,
    description: str,
    startup: Callable[[], Awaitable[None]] | None = None,
    shutdown: Callable[[], Awaitable[None]] | None = None,
    ready_check: Callable[[], Awaitable[bool]] | None = None,
) -> FastAPI:
    configure_logging(settings.service_name, settings.log_level, settings.environment)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(
            "service_starting",
            extra={"version": settings.version, "environment": settings.environment},
        )
        if startup is not None:
            await startup()
        app.state.started = True
        logger.info("service_started")
        try:
            yield
        finally:
            app.state.started = False
            if shutdown is not None:
                await shutdown()
            logger.info("service_stopped")

    app = FastAPI(
        title=title,
        version=settings.version,
        description=description,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.ready_check = ready_check

    install_error_handlers(app, settings.service_name)
    if settings.metrics_enabled:
        install_metrics(app, settings.service_name)

    @app.get("/health/live", tags=["health"], summary="Liveness probe")
    async def live() -> dict:
        return {"status": "alive", "service": settings.service_name, "version": settings.version}

    @app.get("/health/ready", tags=["health"], summary="Readiness probe")
    async def ready() -> JSONResponse:
        ready_ok = True
        detail = "ready"
        check = app.state.ready_check
        if check is not None:
            try:
                ready_ok = await asyncio.wait_for(check(), timeout=3.0)
            except Exception as exc:  # pragma: no cover - runtime dependent
                ready_ok = False
                detail = str(exc)[:200]
        if settings.metrics_enabled:
            SERVICE_UP.labels(service=settings.service_name).set(1 if ready_ok else 0)
        return JSONResponse(
            status_code=200 if ready_ok else 503,
            content={
                "status": "ready" if ready_ok else "not_ready",
                "service": settings.service_name,
                "version": settings.version,
                "detail": detail,
            },
        )

    @app.get("/health/startup", tags=["health"], summary="Startup probe", include_in_schema=False)
    async def startup_probe() -> dict:
        return {"status": "started" if getattr(app.state, "started", False) else "starting"}

    return app
