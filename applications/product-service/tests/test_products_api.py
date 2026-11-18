"""Unit/API tests for product-service inventory semantics."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

SERVICE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))
sys.path.insert(0, str(SERVICE_DIR.parent / "shared"))

TMP = pathlib.Path(tempfile.mkdtemp(prefix="product-service-test-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TMP / 'products.db'}"
os.environ["INTERNAL_API_TOKEN"] = "test-token"
os.environ["LOG_LEVEL"] = "WARNING"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

HEADERS = {"X-Internal-Token": "test-token"}


def _create_product(client: TestClient, sku: str = "SKU-1", stock: int = 5) -> dict:
    response = client.post(
        "/products",
        json={
            "sku": sku,
            "name": f"Widget {sku}",
            "description": "Test widget",
            "price_cents": 1999,
            "stock": stock,
        },
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health_and_auth() -> None:
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/products").status_code == 401


def test_create_and_list_products() -> None:
    with TestClient(app) as client:
        product = _create_product(client, "SKU-LIST")
        assert product["sku"] == "SKU-LIST"
        listed = client.get("/products?limit=50", headers=HEADERS)
        assert listed.status_code == 200
        assert any(item["id"] == product["id"] for item in listed.json()["items"])


def test_duplicate_sku_conflict() -> None:
    with TestClient(app) as client:
        _create_product(client, "SKU-DUP")
        duplicate = client.post(
            "/products",
            json={"sku": "SKU-DUP", "name": "Again", "price_cents": 100, "stock": 1},
            headers=HEADERS,
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "sku_exists"


def test_stock_reservation_and_release() -> None:
    with TestClient(app) as client:
        product = _create_product(client, "SKU-STOCK", stock=10)
        reserved = client.patch(
            f"/products/{product['id']}/stock", json={"delta": -4}, headers=HEADERS
        )
        assert reserved.status_code == 200
        assert reserved.json()["stock"] == 6

        released = client.patch(
            f"/products/{product['id']}/stock", json={"delta": 4}, headers=HEADERS
        )
        assert released.json()["stock"] == 10


def test_insufficient_stock_is_rejected_without_mutation() -> None:
    with TestClient(app) as client:
        product = _create_product(client, "SKU-LOW", stock=2)
        response = client.patch(
            f"/products/{product['id']}/stock", json={"delta": -5}, headers=HEADERS
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "insufficient_stock"
        assert response.json()["error"]["details"]["available"] == 2
        current = client.get(f"/products/{product['id']}", headers=HEADERS)
        assert current.json()["stock"] == 2


def test_product_not_found() -> None:
    with TestClient(app) as client:
        assert client.get("/products/missing", headers=HEADERS).status_code == 404
        assert (
            client.patch("/products/missing/stock", json={"delta": -1}, headers=HEADERS).status_code
            == 404
        )
