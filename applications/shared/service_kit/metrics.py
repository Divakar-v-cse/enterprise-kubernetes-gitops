"""Prometheus metrics with low-cardinality path templates."""

from __future__ import annotations

import time

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests processed",
    ["service", "method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["service", "method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
REQUEST_IN_PROGRESS = Gauge(
    "http_requests_in_progress", "Requests currently being processed", ["service"]
)
SERVICE_UP = Gauge("service_up", "Service readiness indicator (1=ready)", ["service"])


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return "unmatched"


def install_metrics(app: FastAPI, service: str) -> None:
    @app.middleware("http")
    async def _metrics_middleware(request: Request, call_next):
        if request.url.path in {"/metrics", "/health/live"}:
            return await call_next(request)
        started = time.perf_counter()
        REQUEST_IN_PROGRESS.labels(service=service).inc()
        try:
            response = await call_next(request)
        except Exception:
            REQUEST_COUNT.labels(service, request.method, _route_template(request), "500").inc()
            raise
        finally:
            REQUEST_IN_PROGRESS.labels(service=service).dec()
            REQUEST_LATENCY.labels(service, request.method, _route_template(request)).observe(
                time.perf_counter() - started
            )
        REQUEST_COUNT.labels(
            service, request.method, _route_template(request), str(response.status_code)
        ).inc()
        return response

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
