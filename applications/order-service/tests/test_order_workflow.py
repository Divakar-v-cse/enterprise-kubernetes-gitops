"""Order workflow tests: pricing, stock saga, compensation and idempotency.

Downstream services are replaced by in-memory fakes so the saga logic can be
tested deterministically, including failure compensation.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
from types import SimpleNamespace

SERVICE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))
sys.path.insert(0, str(SERVICE_DIR.parent / "shared"))

TMP = pathlib.Path(tempfile.mkdtemp(prefix="order-service-test-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TMP / 'orders.db'}"
os.environ["INTERNAL_API_TOKEN"] = "test-token"
os.environ["LOG_LEVEL"] = "WARNING"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main as order_main  # noqa: E402
from service_kit import UpstreamError  # noqa: E402

HEADERS = {"X-Internal-Token": "test-token"}


class FakeUpstreams:
    """Small stateful stand-in for user/product/notification services."""

    def __init__(self) -> None:
        self.users = {
            "user-1": {"id": "user-1", "email": "ada@example.com", "full_name": "Ada"},
        }
        self.products = {
            "prod-1": {"id": "prod-1", "sku": "SKU-1", "name": "Widget", "price_cents": 1999,
                       "currency": "USD", "stock": 10, "active": True},
            "prod-2": {"id": "prod-2", "sku": "SKU-2", "name": "Gadget", "price_cents": 500,
                       "currency": "USD", "stock": 1, "active": True},
        }
        self.notifications: list[dict] = []
        self.notification_failure = False
        self.stock_calls: list[tuple[str, int]] = []


class FakeClient:
    def __init__(self, name: str, state: FakeUpstreams) -> None:
        self.name = name
        self.state = state

    async def get_json(self, path: str, **kwargs) -> dict:
        if self.name == "users":
            user_id = path.rsplit("/", 1)[-1]
            if user_id not in self.state.users:
                raise UpstreamError(self.name, "not found", 404)
            return self.state.users[user_id]
        if self.name == "products":
            product_id = path.rsplit("/", 1)[-1]
            if product_id not in self.state.products:
                raise UpstreamError(self.name, "not found", 404)
            return self.state.products[product_id]
        raise AssertionError(f"unexpected get_json on {self.name}")

    async def request(self, method: str, path: str, json: dict | None = None, **kwargs):
        product_id = path.split("/")[2]
        product = self.state.products[product_id]
        if method == "PATCH":
            delta = json["delta"]
            self.state.stock_calls.append((product_id, delta))
            if delta < 0 and product["stock"] + delta < 0:
                return SimpleNamespace(status_code=409, json=lambda: {"error": "insufficient"})
            product["stock"] += delta
            return SimpleNamespace(status_code=200, json=lambda: product)
        return SimpleNamespace(status_code=200, json=lambda: product)

    async def post_json(self, path: str, payload: dict, **kwargs) -> dict:
        if self.state.notification_failure:
            raise UpstreamError(self.name, "provider unavailable", 503)
        self.state.notifications.append(payload)
        return {"id": "notif-1", **payload}

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.fixture()
def upstreams() -> FakeUpstreams:
    state = FakeUpstreams()
    order_main.clients.clear()
    order_main.clients.update(
        {
            "users": FakeClient("users", state),
            "products": FakeClient("products", state),
            "notifications": FakeClient("notifications", state),
        }
    )
    return state


def _payload(user_id: str = "user-1", product_id: str = "prod-1", quantity: int = 2) -> dict:
    return {"user_id": user_id, "items": [{"product_id": product_id, "quantity": quantity}]}


def test_create_order_prices_basket_and_reserves_stock(upstreams) -> None:
    with TestClient(order_main.app) as client:
        response = client.post("/orders", json=_payload(), headers=HEADERS)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "confirmed"
        assert body["total_cents"] == 3998
        assert body["items"][0]["quantity"] == 2
    assert upstreams.products["prod-1"]["stock"] == 8
    assert len(upstreams.notifications) == 1
    assert upstreams.notifications[0]["order_id"] == body["id"]


def test_insufficient_stock_rolls_back_earlier_reservations(upstreams) -> None:
    payload = {
        "user_id": "user-1",
        "items": [
            {"product_id": "prod-1", "quantity": 2},
            {"product_id": "prod-2", "quantity": 5},
        ],
    }
    with TestClient(order_main.app) as client:
        response = client.post("/orders", json=payload, headers=HEADERS)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "insufficient_stock"
    # prod-1 was reserved then compensated; prod-2 never changed.
    assert upstreams.products["prod-1"]["stock"] == 10
    assert upstreams.products["prod-2"]["stock"] == 1
    assert (("prod-1", 2) in upstreams.stock_calls)


def test_unknown_user_is_rejected(upstreams) -> None:
    with TestClient(order_main.app) as client:
        response = client.post("/orders", json=_payload(user_id="ghost"), headers=HEADERS)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "unknown_user"


def test_notification_failure_keeps_order_with_pending_status(upstreams) -> None:
    upstreams.notification_failure = True
    with TestClient(order_main.app) as client:
        response = client.post("/orders", json=_payload(quantity=1), headers=HEADERS)
        assert response.status_code == 201
        assert response.json()["status"] == "notification_pending"


def test_idempotency_key_does_not_double_reserve(upstreams) -> None:
    headers = {**HEADERS, "Idempotency-Key": "key-abc"}
    with TestClient(order_main.app) as client:
        first = client.post("/orders", json=_payload(quantity=1), headers=headers)
        second = client.post("/orders", json=_payload(quantity=1), headers=headers)
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
    assert upstreams.products["prod-1"]["stock"] == 9


def test_requires_internal_token(upstreams) -> None:
    with TestClient(order_main.app) as client:
        assert client.post("/orders", json=_payload()).status_code == 401
        assert client.get("/orders").status_code == 401


def test_list_orders_with_pagination(upstreams) -> None:
    with TestClient(order_main.app) as client:
        client.post("/orders", json=_payload(quantity=1), headers=HEADERS)
        listed = client.get("/orders?limit=5&offset=0", headers=HEADERS)
        assert listed.status_code == 200
        assert listed.json()["total"] >= 1
        assert listed.json()["limit"] == 5
