"""Platform API: read-only operational data for the React dashboard.

Security posture:
  * every /api route requires a bearer token (or X-API-Key) except health;
  * the Kubernetes client is read-only and uses a dedicated ServiceAccount;
  * when the cluster is unreachable the API never fabricates "live" data --
    responses carry meta.source="demo" and a reason string.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

from . import demo
from .auth import require_token
from .config import settings
from .kube import cluster

STARTED_AT = time.time()
REQUEST_COUNT = Counter(
    "platform_api_requests_total", "Platform API requests", ["path", "status"]
)
REQUEST_LATENCY = Histogram(
    "platform_api_request_duration_seconds", "Platform API latency", ["path"]
)

app = FastAPI(
    title="Platform API",
    version=settings.version,
    description="Read-only operational API for the Kubernetes GitOps platform dashboard.",
    docs_url="/api/docs" if not settings.is_production else None,
    openapi_url="/api/openapi.json" if not settings.is_production else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-Id"],
    expose_headers=["X-Request-Id", "X-Data-Source"],
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta(source: str, **extra: Any) -> dict:
    payload = {
        "source": source,
        "cluster": settings.cluster_name,
        "generated_at": _now(),
        "demo_mode": source != "cluster",
    }
    payload.update(extra)
    return payload


def _paginate(items: list[dict], limit: int, offset: int) -> tuple[list[dict], dict]:
    window = items[offset: offset + limit]
    return window, {"count": len(window), "total": len(items), "limit": limit, "offset": offset}


def _live() -> bool:
    return cluster.available


async def _collect(kind: str, live_fn: Callable[[], Any], demo_fn: Callable[[], Any]):
    """Return (data, source, reason). Never masks a cluster failure as live data."""
    connected = await asyncio.to_thread(cluster.connect)
    if connected:
        try:
            data = await asyncio.to_thread(cluster.cached, kind, live_fn) if kind else await asyncio.to_thread(live_fn)
            return data, "cluster", None
        except Exception as exc:  # noqa: BLE001 - Kubernetes client errors vary
            return demo_fn(), "demo", f"cluster query failed: {str(exc)[:180]}"
    return demo_fn(), "demo", cluster.error or "cluster not configured"


@app.middleware("http")
async def _observe(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    response.headers["x-response-time-ms"] = f"{(time.perf_counter() - started) * 1000:.2f}"
    if request.url.path.startswith("/api"):
        REQUEST_COUNT.labels(request.url.path, str(response.status_code)).inc()
        REQUEST_LATENCY.labels(request.url.path).observe(time.perf_counter() - started)
    return response


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "Unexpected platform API error",
                           "request_id": request.headers.get("x-request-id", "-")}},
    )


@app.get("/api/health", tags=["health"], summary="Platform and cluster health")
async def health() -> dict:
    connected = await asyncio.to_thread(cluster.connect)
    return {
        "status": "ok" if connected else "degraded",
        "service": settings.service_name,
        "version": settings.version,
        "uptime_seconds": round(time.time() - STARTED_AT, 1),
        "auth_enabled": settings.auth_enabled,
        "cluster": {
            "connected": connected,
            "name": settings.cluster_name,
            "error": None if connected else (cluster.error or "cluster not configured"),
            "data_source": "cluster" if connected else "demo",
        },
        "timestamp": _now(),
    }


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


api = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


@api.get("/clusters", tags=["clusters"], summary="Cluster inventory and health")
async def clusters() -> dict:
    data, source, reason = await _collect("overview", cluster.overview, demo.overview)
    return {
        "data": [{"id": settings.cluster_name, "name": settings.cluster_name, **data}],
        "meta": _meta(source, reason=reason),
    }


@api.get("/namespaces", tags=["namespaces"])
async def namespaces(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=63),
) -> dict:
    data, source, reason = await _collect("namespaces", cluster.namespaces, demo.namespaces)
    if q:
        data = [item for item in data if q.lower() in item["name"].lower()]
    window, page = _paginate(data, limit, offset)
    return {"data": window, "meta": _meta(source, reason=reason, **page)}


@api.get("/workloads", tags=["workloads"])
async def workloads(
    namespace: str | None = Query(None, max_length=63),
    kind: str | None = Query(None, max_length=32),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    data, source, reason = await _collect("workloads", cluster.workloads, demo.workloads)
    if namespace:
        data = [item for item in data if item["namespace"] == namespace]
    if kind:
        data = [item for item in data if item["kind"].lower() == kind.lower()]
    window, page = _paginate(data, limit, offset)
    return {"data": window, "meta": _meta(source, reason=reason, **page)}


@api.get("/pods", tags=["pods"])
async def pods(
    namespace: str | None = Query(None, max_length=63),
    phase: str | None = Query(None, max_length=20),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    data, source, reason = await _collect("pods", cluster.pods, demo.pods)
    if namespace:
        data = [item for item in data if item["namespace"] == namespace]
    if phase:
        data = [item for item in data if item["phase"].lower() == phase.lower()]
    window, page = _paginate(data, limit, offset)
    return {"data": window, "meta": _meta(source, reason=reason, **page)}


@api.get("/deployments", tags=["deployments"])
async def deployments(
    namespace: str | None = Query(None, max_length=63),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    data, source, reason = await _collect("deployments", cluster.deployments, demo.deployments)
    if namespace:
        data = [item for item in data if item["namespace"] == namespace]
    window, page = _paginate(data, limit, offset)
    return {"data": window, "meta": _meta(source, reason=reason, **page)}


@api.get("/services", tags=["services"])
async def services(
    namespace: str | None = Query(None, max_length=63),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    data, source, reason = await _collect("services", cluster.services, demo.services)
    if namespace:
        data = [item for item in data if item["namespace"] == namespace]
    window, page = _paginate(data, limit, offset)
    return {"data": window, "meta": _meta(source, reason=reason, **page)}


@api.get("/metrics", tags=["monitoring"])
async def metrics_summary() -> dict:
    data, source, reason = await _collect("metrics", cluster.metrics, demo.metrics)
    return {"data": data, "meta": _meta(source, reason=reason)}


@api.get("/alerts", tags=["alerting"])
async def alerts(
    severity: str | None = Query(None, max_length=20),
    status_filter: str | None = Query(None, alias="status", max_length=20),
) -> dict:
    data, source, reason = await _collect("alerts", cluster.alerts, demo.alerts)
    if severity:
        data = [item for item in data if item["severity"].lower() == severity.lower()]
    if status_filter:
        data = [item for item in data if item["status"].lower() == status_filter.lower()]
    return {
        "data": data,
        "meta": _meta(
            source, reason=reason,
            firing=sum(1 for item in data if item["status"] == "firing"),
            critical=sum(1 for item in data if item["severity"] == "critical"),
        ),
    }


@api.get("/gitops/status", tags=["gitops"])
async def gitops_status() -> dict:
    data, source, reason = await _collect("gitops", cluster.gitops, demo.gitops)
    return {
        "data": data,
        "meta": _meta(
            source, reason=reason,
            synced=sum(1 for item in data if item["sync_status"] == "Synced"),
            out_of_sync=sum(1 for item in data if item["sync_status"] != "Synced"),
            degraded=sum(1 for item in data if item["health_status"] not in {"Healthy"}),
        ),
    }


@api.get("/security/findings", tags=["security"])
async def security_findings(
    severity: str | None = Query(None, max_length=20),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    payload = cluster.security()
    findings = payload.get("findings", [])
    if severity:
        findings = [item for item in findings if item.get("severity", "").lower() == severity.lower()]
    window, page = _paginate(findings, limit, offset)
    return {
        "data": {
            "summary": payload.get("summary", {}),
            "scanners": payload.get("scanners", []),
            "generated_at": payload.get("generated_at"),
            "findings": window,
            "note": payload.get("note", ""),
        },
        "meta": _meta("security-scan", **page),
    }


@api.get("/logs", tags=["logs"])
async def logs(
    namespace: str | None = Query(None, max_length=63),
    pod: str | None = Query(None, max_length=253),
    level: str | None = Query(None, pattern="^(?i)(debug|info|warning|warn|error|critical)$"),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    connected = await asyncio.to_thread(cluster.connect)
    if connected:
        try:
            data = await asyncio.to_thread(cluster.logs, namespace, pod, level, limit)
            return {"data": data, "meta": _meta("cluster", count=len(data), limit=limit)}
        except Exception as exc:  # noqa: BLE001
            reason = f"log backend unavailable: {str(exc)[:160]}"
    else:
        reason = cluster.error or "cluster not configured"
    data = demo.logs()
    if level:
        data = [item for item in data if item["level"].lower() == level.lower()]
    return {"data": data[:limit], "meta": _meta("demo", reason=reason, count=len(data[:limit]),
                                                limit=limit)}


app.include_router(api)
