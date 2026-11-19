"""Unit tests for the Kubernetes collector helpers and demo dataset.

These cover the pure parsing/serialisation logic that the HTTP tests cannot
reach, and keep the coverage gate meaningful for the platform API.
"""

from __future__ import annotations

import os
import pathlib
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

SERVICE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

os.environ["PLATFORM_DEMO_MODE"] = "true"
os.environ["PLATFORM_AUTH_ENABLED"] = "true"
os.environ["PLATFORM_API_TOKEN"] = "test-token"

from app import demo  # noqa: E402
from app.config import settings  # noqa: E402
from app.kube import (  # noqa: E402
    ClusterAccess,
    _last_value,
    _pods_by_namespace,
    _unit_for,
    age_of,
    parse_cpu,
    parse_memory_mib,
)


# ---------------------------------------------------------------- parsing
def test_parse_cpu_handles_units():
    assert parse_cpu("1") == 1.0
    assert parse_cpu("250m") == 0.25
    assert parse_cpu("1500000n") == 0.0015
    assert parse_cpu(None) == 0.0
    assert parse_cpu("not-a-number") == 0.0


def test_parse_memory_returns_mebibytes():
    assert parse_memory_mib("1Gi") == 1024
    assert parse_memory_mib("512Mi") == 512
    assert parse_memory_mib("1048576Ki") == 1024
    # Unit-less values are bytes.
    assert parse_memory_mib("1048576") == 1
    assert parse_memory_mib(None) == 0.0
    assert parse_memory_mib("garbage") == 0.0


def test_age_of_formats_ranges():
    now = datetime.now(UTC)
    assert age_of(now - timedelta(seconds=30)) == "0m"
    assert age_of(now - timedelta(minutes=5)) == "5m"
    assert age_of(now - timedelta(hours=3)).startswith("3h")
    assert age_of(now - timedelta(days=2)).endswith("h")
    assert age_of(None) == "unknown"


# ---------------------------------------------------------------- helpers
def test_pods_by_namespace_counts_kube_objects():
    pods = [
        SimpleNamespace(metadata=SimpleNamespace(namespace="platform")),
        SimpleNamespace(metadata=SimpleNamespace(namespace="platform")),
        SimpleNamespace(metadata=SimpleNamespace(namespace="monitoring")),
    ]
    counts = _pods_by_namespace(pods)
    assert counts["platform"] == 2
    assert counts["monitoring"] == 1


def test_unit_for_falls_back_to_empty_string():
    assert _unit_for("definitely-not-a-metric") == ""


def test_last_value_reads_final_sample():
    series = [
        {"name": "cpu", "points": [{"v": 0.2}, {"v": 0.4}]},
        {"name": "memory", "points": [{"v": 0.9}]},
    ]
    assert _last_value(series, "cpu") == 0.4
    assert _last_value([], "cpu") == 0.0
    assert _last_value([{"name": "cpu", "points": []}], "cpu") == 0.0


def test_security_reads_findings_file(tmp_path, monkeypatch):
    findings = tmp_path / "findings.json"
    findings.write_text(
        '{"summary": {"critical": 0, "high": 1, "medium": 0, "low": 0, "total": 1},'
        ' "findings": [{"id": "X1", "severity": "high"}], "scanners": ["trivy"]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "security_findings_path", str(findings), raising=False)
    data = ClusterAccess().security()
    assert data["summary"]["high"] == 1
    assert data["findings"][0]["id"] == "X1"


def test_cache_returns_cached_value_within_ttl():
    access = ClusterAccess()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return {"value": calls["n"]}

    first = access.cached("overview", fn)
    second = access.cached("overview", fn)
    assert first == second == {"value": 1}
    assert calls["n"] == 1


def test_cluster_access_reports_unavailable_without_kubeconfig(monkeypatch):
    access = ClusterAccess()

    def boom(*_args, **_kwargs):
        raise RuntimeError("no config")

    monkeypatch.setattr("app.kube.config.load_kube_config", boom)
    monkeypatch.setattr("app.kube.config.load_incluster_config", boom)
    assert access.connect(force=True) is False
    assert access.available is False
    assert access.error


# ---------------------------------------------------------------- demo data
def test_demo_overview_shape():
    data = demo.overview()
    assert data["nodes"]["total"] >= 1
    assert data["pods"]["running"] > 0
    assert data["deployments"]["total"] >= 1
    assert data["namespaces"] >= 1


def test_demo_lists_are_non_empty_and_consistent():
    pods = demo.pods()
    assert pods and all({"name", "namespace", "phase"} <= set(p) for p in pods)
    deployments = demo.deployments()
    assert deployments and all(d["ready"] <= d["desired"] for d in deployments)
    assert demo.namespaces()
    assert demo.services()
    assert demo.workloads()


def test_demo_metrics_and_alerts():
    metrics = demo.metrics()
    assert isinstance(metrics["summary"], dict)
    assert metrics["series"]
    assert all("points" in series for series in metrics["series"])
    alerts = demo.alerts()
    assert isinstance(alerts, list)
    assert all({"name", "severity", "status"} <= set(a) for a in alerts)


def test_demo_gitops_security_and_logs():
    apps = demo.gitops()
    assert apps and {"name", "sync_status", "health_status"} <= set(apps[0])
    findings = demo.security()
    assert "summary" in findings and "findings" in findings
    logs = demo.logs()
    assert logs and {"timestamp", "level", "service", "message"} <= set(logs[0])
