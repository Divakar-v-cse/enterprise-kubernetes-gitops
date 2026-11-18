"""Unit/API tests for notification-service dispatch + idempotency."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

SERVICE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))
sys.path.insert(0, str(SERVICE_DIR.parent / "shared"))

TMP = pathlib.Path(tempfile.mkdtemp(prefix="notification-service-test-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TMP / 'notifications.db'}"
os.environ["INTERNAL_API_TOKEN"] = "test-token"
os.environ["NOTIFICATION_FAILURE_RATE"] = "0"
os.environ["LOG_LEVEL"] = "WARNING"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

HEADERS = {"X-Internal-Token": "test-token"}
PAYLOAD = {
    "order_id": "order-123",
    "user_id": "user-123",
    "recipient": "customer@example.com",
    "channel": "email",
    "subject": "Order confirmed",
    "message": "Thanks for your order.",
}


def test_dispatch_creates_sent_notification() -> None:
    with TestClient(app) as client:
        response = client.post("/notifications", json=PAYLOAD, headers=HEADERS)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "sent"
        assert body["attempts"] == 1
        assert body["sent_at"] is not None


def test_duplicate_dispatch_is_idempotent() -> None:
    with TestClient(app) as client:
        first = client.post("/notifications", json=PAYLOAD, headers=HEADERS).json()
        second = client.post("/notifications", json=PAYLOAD, headers=HEADERS).json()
        assert first["id"] == second["id"]
        listed = client.get("/notifications?order_id=order-123", headers=HEADERS).json()
        assert listed["total"] == 1


def test_filter_by_status_and_order() -> None:
    with TestClient(app) as client:
        listed = client.get("/notifications?status=sent", headers=HEADERS)
        assert listed.status_code == 200
        assert all(item["status"] == "sent" for item in listed.json()["items"])


def test_retry_unknown_notification_returns_404() -> None:
    with TestClient(app) as client:
        response = client.post("/notifications/missing/retry", headers=HEADERS)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "notification_not_found"


def test_validation_rejects_bad_channel() -> None:
    with TestClient(app) as client:
        bad = {**PAYLOAD, "channel": "carrier-pigeon", "order_id": "order-999"}
        response = client.post("/notifications", json=bad, headers=HEADERS)
        assert response.status_code == 422
