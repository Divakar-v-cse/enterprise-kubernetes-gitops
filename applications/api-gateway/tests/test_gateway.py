"""Gateway contract tests: auth, aggregation, proxying and rate limiting."""

from __future__ import annotations

import os
import pathlib
import sys
from types import SimpleNamespace

SERVICE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))
sys.path.insert(0, str(SERVICE_DIR.parent / "shared"))

os.environ["LOG_LEVEL"] = "WARNING"
os.environ["INTERNAL_API_TOKEN"] = "test-token"
os.environ["AUTH_ENABLED"] = "true"
os.environ["PUBLIC_API_KEY"] = "test-public-key"
os.environ["RATE_LIMIT_PER_MINUTE"] = "5"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main as gateway  # noqa: E402
from service_kit import UpstreamError  # noqa: E402


class FakeClient:
    def __init__(self, name: str, healthy: bool = True) -> None:
        self.name = name
        self.healthy = healthy
        self.calls: list[str] = []

    async def request(self, method: str, path: str, **kwargs):
        self.calls.append(f"{method} {path}")
        if not self.healthy:
            raise UpstreamError(self.name, "connection refused")
        if path.startswith("/health/ready"):
            return SimpleNamespace(status_code=200, json=lambda: {"status": "ready"})
        if path.startswith("/products"):
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"items": [{"id": "prod-1", "name": "Widget"}], "total": 1},
            )
        if path.startswith("/orders"):
            return SimpleNamespace(status_code=200, json=lambda: {"items": [], "total": 0})
        if method == "POST":
            return SimpleNamespace(status_code=201, json=lambda: {"id": "created"})
        return SimpleNamespace(status_code=200, json=lambda: {"items": [], "total": 0})

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.fixture()
def fake_upstreams() -> dict[str, FakeClient]:
    services = {
        name: FakeClient(name)
        for name in ("user-service", "product-service", "order-service", "notification-service")
    }
    gateway.clients.clear()
    gateway.clients.update(services)
    gateway._buckets.clear()
    return services


def test_health_aggregates_all_dependencies(fake_upstreams) -> None:
    with TestClient(gateway.app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert set(body["dependencies"]) == set(fake_upstreams)


def test_health_reports_degraded_when_dependency_is_down(fake_upstreams) -> None:
    gateway.clients["order-service"].healthy = False
    with TestClient(gateway.app) as client:
        body = client.get("/api/health").json()
        assert body["status"] == "degraded"
        assert body["dependencies"]["order-service"]["status"] == "down"


def test_writes_require_api_key(fake_upstreams) -> None:
    with TestClient(gateway.app) as client:
        unauthorized = client.post("/api/users", json={"email": "a@b.com", "full_name": "AB"})
        assert unauthorized.status_code == 401
        assert unauthorized.json()["error"]["code"] == "unauthorized"
        authorized = client.post(
            "/api/users",
            json={"email": "a@b.com", "full_name": "AB"},
            headers={"X-API-Key": "test-public-key"},
        )
        assert authorized.status_code == 201


def test_reads_are_public_and_proxied(fake_upstreams) -> None:
    with TestClient(gateway.app) as client:
        response = client.get("/api/products?limit=5")
        assert response.status_code == 200
        assert response.json()["items"][0]["name"] == "Widget"
    assert "GET /products" in fake_upstreams["product-service"].calls


def test_catalog_overview_aggregates_fanout(fake_upstreams) -> None:
    with TestClient(gateway.app) as client:
        body = client.get("/api/catalog/overview").json()
        assert body["product_total"] == 1
        assert body["recent_orders"] == []


def test_upstream_outage_maps_to_503(fake_upstreams) -> None:
    gateway.clients["product-service"].healthy = False
    with TestClient(gateway.app) as client:
        response = client.get("/api/products")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "dependency_unavailable"


def test_rate_limit_returns_429(fake_upstreams) -> None:
    with TestClient(gateway.app) as client:
        for _ in range(5):
            assert client.get("/api/products").status_code == 200
        limited = client.get("/api/products")
        assert limited.status_code == 429
        assert limited.headers["Retry-After"] == "30"


def test_request_id_is_propagated(fake_upstreams) -> None:
    with TestClient(gateway.app) as client:
        response = client.get("/api/products", headers={"X-Request-Id": "req-123"})
        assert response.headers["x-request-id"] == "req-123"
