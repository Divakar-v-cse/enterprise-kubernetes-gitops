"""Unit/API tests for user-service (SQLite-backed, no external services)."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

SERVICE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))
sys.path.insert(0, str(SERVICE_DIR.parent / "shared"))

TMP = pathlib.Path(tempfile.mkdtemp(prefix="user-service-test-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TMP / 'users.db'}"
os.environ["INTERNAL_API_TOKEN"] = "test-token"
os.environ["LOG_LEVEL"] = "WARNING"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

HEADERS = {"X-Internal-Token": "test-token"}


def _client() -> TestClient:
    return TestClient(app)


def test_liveness_and_readiness() -> None:
    with _client() as client:
        live = client.get("/health/live")
        assert live.status_code == 200
        assert live.json()["status"] == "alive"
        ready = client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"


def test_metrics_endpoint_exposes_prometheus_format() -> None:
    with _client() as client:
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "http_requests_total" in response.text


def test_rejects_missing_internal_token() -> None:
    with _client() as client:
        response = client.get("/users")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


def test_create_list_and_fetch_user() -> None:
    with _client() as client:
        created = client.post(
            "/users",
            json={"email": "ada@example.com", "full_name": "Ada Lovelace", "tier": "premium"},
            headers=HEADERS,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["email"] == "ada@example.com"
        assert body["tier"] == "premium"

        listed = client.get("/users?limit=10&offset=0", headers=HEADERS)
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        assert listed.json()["items"][0]["id"] == body["id"]

        fetched = client.get(f"/users/{body['id']}", headers=HEADERS)
        assert fetched.status_code == 200
        assert fetched.json()["full_name"] == "Ada Lovelace"


def test_duplicate_email_conflict() -> None:
    payload = {"email": "grace@example.com", "full_name": "Grace Hopper"}
    with _client() as client:
        assert client.post("/users", json=payload, headers=HEADERS).status_code == 201
        duplicate = client.post("/users", json=payload, headers=HEADERS)
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "email_exists"


def test_validation_error_envelope() -> None:
    with _client() as client:
        response = client.post(
            "/users", json={"email": "not-an-email", "full_name": "X"}, headers=HEADERS
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def test_unknown_user_returns_404() -> None:
    with _client() as client:
        response = client.get("/users/does-not-exist", headers=HEADERS)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "user_not_found"


def test_pagination_bounds_are_enforced() -> None:
    with _client() as client:
        assert client.get("/users?limit=0", headers=HEADERS).status_code == 422
        assert client.get("/users?limit=101", headers=HEADERS).status_code == 422
        assert client.get("/users?offset=-1", headers=HEADERS).status_code == 422
