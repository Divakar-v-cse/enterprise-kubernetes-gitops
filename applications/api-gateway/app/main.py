"""Edge API gateway.

Owns the public contract: CORS, API-key protection for writes, per-client rate
limiting, request correlation, fan-out health aggregation and resilient
proxying to the four domain services.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from fastapi import Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter
from service_kit import (
    ApiError,
    BaseSettings,
    CircuitOpenError,
    ServiceClient,
    UpstreamError,
    build_app,
    get_logger,
)

logger = get_logger("gateway")

GATEWAY_REQUESTS = Counter(
    "gateway_requests_total", "Requests handled by the gateway", ["route", "outcome"]
)
RATE_LIMITED = Counter("gateway_rate_limited_total", "Requests rejected by rate limiting")


@dataclass
class Settings(BaseSettings):
    service_name: str = "api-gateway"
    public_api_key: str = field(default_factory=lambda: os.getenv("PUBLIC_API_KEY", "demo-public-key"))
    auth_enabled: bool = field(
        default_factory=lambda: os.getenv("AUTH_ENABLED", "true").lower() == "true"
    )
    rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "240"))
    )
    cors_origins: str = field(
        default_factory=lambda: os.getenv(
            "CORS_ALLOW_ORIGINS", "http://localhost:5173,http://localhost:3000,http://localhost:8080"
        )
    )


settings = Settings(service_name="api-gateway")
clients = {
    "user-service": ServiceClient(
        "user-service", os.getenv("USER_SERVICE_URL", "http://localhost:8001"),
        timeout=settings.request_timeout_seconds, token=settings.internal_token,
    ),
    "product-service": ServiceClient(
        "product-service", os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8002"),
        timeout=settings.request_timeout_seconds, token=settings.internal_token,
    ),
    "order-service": ServiceClient(
        "order-service", os.getenv("ORDER_SERVICE_URL", "http://localhost:8003"),
        timeout=settings.request_timeout_seconds, token=settings.internal_token,
    ),
    "notification-service": ServiceClient(
        "notification-service", os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8004"),
        timeout=settings.request_timeout_seconds, token=settings.internal_token,
    ),
}

_buckets: dict[str, deque[float]] = defaultdict(deque)


def _rate_limited(client: str) -> bool:
    window = _buckets[client]
    now = time.monotonic()
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= settings.rate_limit_per_minute:
        return True
    window.append(now)
    return False


async def _startup() -> None:
    for client in clients.values():
        await client.start()
    logger.info("gateway_ready", extra={"upstreams": list(clients)})


async def _shutdown() -> None:
    for client in clients.values():
        await client.close()


async def _ready() -> bool:
    return True


app = build_app(
    settings,
    title="API Gateway",
    description="Public entry point for the storefront and internal service mesh.",
    startup=_startup,
    shutdown=_shutdown,
    ready_check=_ready,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-Request-Id", "Idempotency-Key"],
    expose_headers=["X-Request-Id", "X-Response-Time-Ms"],
)


@app.middleware("http")
async def _rate_limit(request: Request, call_next):
    if request.url.path in {"/health/live", "/health/ready", "/metrics"}:
        return await call_next(request)
    client_ip = request.client.host if request.client else "unknown"
    if _rate_limited(client_ip):
        RATE_LIMITED.inc()
        GATEWAY_REQUESTS.labels("rate_limit", "rejected").inc()
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "rate_limited",
                    "message": "Too many requests, retry shortly",
                    "request_id": request.headers.get("x-request-id", "-"),
                }
            },
            headers={"Retry-After": "30"},
        )
    return await call_next(request)


async def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if not settings.auth_enabled:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.public_api_key):
        raise ApiError(401, "unauthorized", "A valid X-API-Key header is required for writes")


async def _forward(
    request: Request, target: str, path: str, *, method: str = "GET", require_body: bool = False
) -> JSONResponse:
    client = clients[target]
    body = None
    if require_body:
        try:
            body = await request.json()
        except Exception as exc:
            raise ApiError(400, "invalid_json", "Request body must be valid JSON") from exc
    headers = {"x-request-id": request.headers.get("x-request-id", "")}
    idem = request.headers.get("idempotency-key")
    if idem:
        headers["idempotency-key"] = idem
    try:
        response = await client.request(
            method, path, json=body, headers=headers, params=dict(request.query_params)
        )
    except CircuitOpenError as exc:
        GATEWAY_REQUESTS.labels(target, "circuit_open").inc()
        raise ApiError(
            503, "dependency_unavailable", f"{target} circuit breaker is open",
            {"target": target, "retryable": True},
        ) from exc
    except UpstreamError as exc:
        GATEWAY_REQUESTS.labels(target, "unavailable").inc()
        raise ApiError(
            503, "dependency_unavailable", f"{target} is unreachable",
            {"target": target, "retryable": True},
        ) from exc

    GATEWAY_REQUESTS.labels(target, "success" if response.status_code < 400 else "error").inc()
    try:
        payload = response.json()
    except ValueError:
        payload = {"data": response.text}
    return JSONResponse(status_code=response.status_code, content=payload)


@app.get("/api/health", tags=["health"], summary="Aggregated dependency health")
async def api_health() -> dict:
    async def probe(name: str, client: ServiceClient) -> tuple[str, dict]:
        started = time.perf_counter()
        try:
            response = await client.request("GET", "/health/ready")
            latency = round((time.perf_counter() - started) * 1000, 2)
            return name, {"status": "ok" if response.status_code == 200 else "degraded",
                          "http_status": response.status_code, "latency_ms": latency}
        except Exception as exc:
            return name, {"status": "down", "error": str(exc)[:120],
                          "latency_ms": round((time.perf_counter() - started) * 1000, 2)}

    results = await asyncio.gather(*(probe(name, client) for name, client in clients.items()))
    services = dict(results)
    overall = "ok" if all(s["status"] == "ok" for s in services.values()) else "degraded"
    return {"status": overall, "service": settings.service_name, "version": settings.version,
            "dependencies": services}


@app.get("/api/users", tags=["users"])
async def list_users(request: Request) -> JSONResponse:
    return await _forward(request, "user-service", "/users")


@app.post("/api/users", tags=["users"], status_code=201,
          dependencies=[Depends(require_api_key)])
async def create_user(request: Request) -> JSONResponse:
    return await _forward(request, "user-service", "/users", method="POST", require_body=True)


@app.get("/api/users/{user_id}", tags=["users"])
async def get_user(user_id: str, request: Request) -> JSONResponse:
    return await _forward(request, "user-service", f"/users/{user_id}")


@app.get("/api/products", tags=["products"])
async def list_products(request: Request) -> JSONResponse:
    return await _forward(request, "product-service", "/products")


@app.post("/api/products", tags=["products"], status_code=201,
          dependencies=[Depends(require_api_key)])
async def create_product(request: Request) -> JSONResponse:
    return await _forward(request, "product-service", "/products", method="POST", require_body=True)


@app.get("/api/products/{product_id}", tags=["products"])
async def get_product(product_id: str, request: Request) -> JSONResponse:
    return await _forward(request, "product-service", f"/products/{product_id}")


@app.get("/api/orders", tags=["orders"])
async def list_orders(request: Request) -> JSONResponse:
    return await _forward(request, "order-service", "/orders")


@app.post("/api/orders", tags=["orders"], status_code=201,
          dependencies=[Depends(require_api_key)])
async def create_order(request: Request) -> JSONResponse:
    return await _forward(request, "order-service", "/orders", method="POST", require_body=True)


@app.get("/api/orders/{order_id}", tags=["orders"])
async def get_order(order_id: str, request: Request) -> JSONResponse:
    return await _forward(request, "order-service", f"/orders/{order_id}")


@app.get("/api/notifications", tags=["notifications"])
async def list_notifications(request: Request) -> JSONResponse:
    return await _forward(request, "notification-service", "/notifications")


@app.get("/api/catalog/overview", tags=["storefront"], summary="Storefront aggregate")
async def catalog_overview(request: Request) -> dict:
    """Fan-out aggregation: products + latest order count in one round trip."""
    products_task = clients["product-service"].request("GET", "/products", params={"limit": 12})
    orders_task = clients["order-service"].request("GET", "/orders", params={"limit": 5})
    try:
        products_response, orders_response = await asyncio.gather(products_task, orders_task)
    except Exception as exc:
        raise ApiError(503, "dependency_unavailable", "Catalog aggregation failed",
                       {"error": str(exc)[:120]}) from exc
    products = products_response.json() if products_response.status_code == 200 else {"items": []}
    orders = orders_response.json() if orders_response.status_code == 200 else {"items": []}
    return {
        "products": products.get("items", []),
        "product_total": products.get("total", 0),
        "recent_orders": orders.get("items", []),
    }
