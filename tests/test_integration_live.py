"""Live integration tests against a running stack (Docker Compose or Kind ingress).

Skipped automatically when the gateway is unreachable, so unit CI stays fast.
Run with:  docker compose up -d --build  &&  pytest tests/test_integration_live.py
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

GATEWAY = os.getenv("GATEWAY_URL", "http://localhost:18005")
API_KEY = os.getenv("PUBLIC_API_KEY", "demo-public-key")
HEADERS = {"X-API-Key": API_KEY}


def _gateway_up() -> bool:
    try:
        return httpx.get(f"{GATEWAY}/health/live", timeout=3).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _gateway_up(), reason="live gateway not reachable")


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    with httpx.Client(base_url=GATEWAY, timeout=15.0) as http:
        yield http


def _create_user(client: httpx.Client) -> dict:
    email = f"it-{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/users", headers=HEADERS,
        json={"email": email, "full_name": "Integration Tester", "tier": "standard"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_product(client: httpx.Client, stock: int = 10) -> dict:
    sku = f"IT-{uuid.uuid4().hex[:8].upper()}"
    response = client.post(
        "/api/products", headers=HEADERS,
        json={"sku": sku, "name": f"Integration {sku}", "price_cents": 1299, "stock": stock},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_dependency_health_is_green(client: httpx.Client) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert all(dep["status"] == "ok" for dep in body["dependencies"].values())


def test_order_lifecycle_decrements_stock_and_notifies(client: httpx.Client) -> None:
    user = _create_user(client)
    product = _create_product(client, stock=10)
    key = str(uuid.uuid4())
    order = client.post(
        "/api/orders",
        headers={**HEADERS, "Idempotency-Key": key},
        json={"user_id": user["id"], "items": [{"product_id": product["id"], "quantity": 3}]},
    )
    assert order.status_code == 201, order.text
    body = order.json()
    assert body["status"] == "confirmed"
    assert body["total_cents"] == 1299 * 3

    stock = client.get(f"/api/products/{product['id']}", headers=HEADERS).json()["stock"]
    assert stock == 7

    notes = client.get(f"/api/notifications?order_id={body['id']}", headers=HEADERS).json()
    assert notes["total"] == 1
    assert notes["items"][0]["status"] == "sent"

    replay = client.post(
        "/api/orders",
        headers={**HEADERS, "Idempotency-Key": key},
        json={"user_id": user["id"], "items": [{"product_id": product["id"], "quantity": 3}]},
    )
    assert replay.json()["id"] == body["id"]
    assert client.get(f"/api/products/{product['id']}", headers=HEADERS).json()["stock"] == 7


def test_insufficient_stock_is_rejected_and_stock_untouched(client: httpx.Client) -> None:
    user = _create_user(client)
    product = _create_product(client, stock=1)
    response = client.post(
        "/api/orders", headers=HEADERS,
        json={"user_id": user["id"], "items": [{"product_id": product["id"], "quantity": 5}]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "insufficient_stock"
    assert client.get(f"/api/products/{product['id']}", headers=HEADERS).json()["stock"] == 1


def test_writes_require_api_key(client: httpx.Client) -> None:
    response = client.post("/api/users", json={"email": "nokey@example.com", "full_name": "No Key"})
    assert response.status_code == 401


def test_metrics_expose_service_counters(client: httpx.Client) -> None:
    metrics = client.get("/metrics").text
    assert "http_requests_total" in metrics
    assert 'service="api-gateway"' in metrics


def test_pagination_contract(client: httpx.Client) -> None:
    page = client.get("/api/orders?limit=2&offset=0", headers=HEADERS).json()
    assert page["limit"] == 2
    assert page["offset"] == 0
    assert len(page["items"]) <= 2
