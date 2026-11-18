"""Platform API contract tests (demo mode, no cluster required)."""

from __future__ import annotations

import os
import pathlib
import sys

SERVICE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

os.environ["PLATFORM_DEMO_MODE"] = "true"
os.environ["PLATFORM_AUTH_ENABLED"] = "true"
os.environ["PLATFORM_API_TOKEN"] = "test-token"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

AUTH = {"Authorization": "Bearer test-token"}


def test_health_is_public_and_reports_demo_mode() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["cluster"]["connected"] is False
        assert body["cluster"]["data_source"] == "demo"
        assert body["auth_enabled"] is True


def test_requires_bearer_token() -> None:
    with TestClient(app) as client:
        assert client.get("/api/pods").status_code == 401
        assert client.get("/api/pods", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/api/pods", headers=AUTH).status_code == 200


def test_pods_pagination_and_source_label() -> None:
    with TestClient(app) as client:
        response = client.get("/api/pods?limit=5&offset=0", headers=AUTH)
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["source"] == "demo"
        assert body["meta"]["demo_mode"] is True
        assert body["meta"]["count"] == 5
        assert body["meta"]["total"] > 5


def test_pods_filter_by_namespace_and_phase() -> None:
    with TestClient(app) as client:
        body = client.get("/api/pods?namespace=platform&phase=Failed", headers=AUTH).json()
        assert body["data"]
        assert all(item["namespace"] == "platform" for item in body["data"])
        assert all(item["phase"] == "Failed" for item in body["data"])


def test_invalid_pagination_is_rejected() -> None:
    with TestClient(app) as client:
        assert client.get("/api/pods?limit=0", headers=AUTH).status_code == 422
        assert client.get("/api/pods?limit=500", headers=AUTH).status_code == 422
        assert client.get("/api/logs?limit=0", headers=AUTH).status_code == 422


def test_overview_endpoint_shape() -> None:
    with TestClient(app) as client:
        body = client.get("/api/clusters", headers=AUTH).json()
        cluster = body["data"][0]
        assert cluster["nodes"]["total"] >= 1
        assert "pods" in cluster and "deployments" in cluster
        assert body["meta"]["source"] == "demo"


def test_metrics_series_and_summary() -> None:
    with TestClient(app) as client:
        body = client.get("/api/metrics", headers=AUTH).json()
        names = {item["name"] for item in body["data"]["series"]}
        assert {"cpu_utilization", "memory_utilization"}.issubset(names)
        assert body["data"]["summary"]["nodes"] >= 1


def test_gitops_status_meta_counts() -> None:
    with TestClient(app) as client:
        body = client.get("/api/gitops/status", headers=AUTH).json()
        assert body["meta"]["synced"] + body["meta"]["out_of_sync"] == len(body["data"])
        assert body["data"][0]["path"].startswith("helm/")


def test_alerts_filtering() -> None:
    with TestClient(app) as client:
        body = client.get("/api/alerts?severity=warning", headers=AUTH).json()
        assert body["meta"]["firing"] >= 1
        assert all(item["severity"] == "warning" for item in body["data"])


def test_security_findings_shape() -> None:
    with TestClient(app) as client:
        body = client.get("/api/security/findings?limit=5", headers=AUTH).json()
        assert "summary" in body["data"]
        assert body["meta"]["source"] == "security-scan"


def test_logs_level_filter() -> None:
    with TestClient(app) as client:
        body = client.get("/api/logs?level=error", headers=AUTH).json()
        assert body["data"]
        assert all(item["level"] == "ERROR" for item in body["data"])


def test_metrics_endpoint_exposes_prometheus_text() -> None:
    with TestClient(app) as client:
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "platform_api_requests_total" in response.text
