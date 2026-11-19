"""Clearly-labelled demo dataset.

Used only when the Kubernetes API is unreachable or PLATFORM_DEMO_MODE=true.
Every payload built here is returned with meta.source="demo" so the dashboard
can show a persistent DEMO badge instead of pretending this is live data.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

NOW = datetime.now(UTC)

SERVICES = [
    ("api-gateway", 2, "platform"),
    ("user-service", 2, "platform"),
    ("product-service", 2, "platform"),
    ("order-service", 2, "platform"),
    ("notification-service", 2, "platform"),
    ("frontend", 2, "platform"),
    ("platform-api", 1, "platform"),
    ("postgres", 1, "platform"),
]


def _age(minutes: int) -> str:
    delta = timedelta(minutes=minutes)
    days = delta.days
    hours = delta.seconds // 3600
    if days:
        return f"{days}d{hours}h"
    return f"{hours}h{(delta.seconds % 3600) // 60}m"


def overview() -> dict:
    return {
        "cluster": {
            "name": "gitops-platform",
            "version": "v1.34.0",
            "provider": "kind (Docker Desktop)",
            "status": "Ready",
            "created_at": (NOW - timedelta(days=3)).isoformat(),
        },
        "nodes": {"total": 1, "ready": 1, "cpu_capacity_cores": 4.0, "memory_capacity_gib": 3.0},
        "pods": {"total": 22, "running": 20, "pending": 1, "failed": 1, "succeeded": 0},
        "deployments": {"total": 13, "available": 12, "unavailable": 1},
        "namespaces": 9,
        "pods_by_namespace": {
            "platform": 14, "monitoring": 5, "argocd": 2, "logging": 1, "kube-system": 8,
        },
        "resource_usage": {"cpu_millicores": 640, "memory_mib": 2150, "cpu_percent": 16.0,
                           "memory_percent": 70.0},
        "alerts": {"firing": 2, "critical": 0},
        "gitops": {"applications": 6, "synced": 5, "out_of_sync": 1, "degraded": 0},
        "throughput_rps": 12.4,
        "error_rate_percent": 0.6,
    }


def namespaces() -> list[dict]:
    rows = [
        ("platform", "Active", 14, {"app.kubernetes.io/part-of": "gitops-platform"}),
        ("monitoring", "Active", 5, {"purpose": "observability"}),
        ("logging", "Active", 1, {"purpose": "logging"}),
        ("argocd", "Active", 2, {"purpose": "gitops"}),
        ("security", "Active", 0, {"purpose": "scanning"}),
        ("kube-system", "Active", 8, {}),
        ("local-path-storage", "Active", 1, {}),
        ("default", "Active", 0, {}),
        ("kube-public", "Active", 0, {}),
    ]
    return [
        {"name": name, "status": status, "pods": pods, "labels": labels, "age": _age(4300 + index * 7)}
        for index, (name, status, pods, labels) in enumerate(rows)
    ]


def pods() -> list[dict]:
    rows: list[dict] = []
    for index, (name, replicas, namespace) in enumerate(SERVICES):
        for replica in range(replicas):
            restarts = 0
            phase = "Running"
            ready = "1/1"
            if name == "order-service" and replica == 1:
                restarts, phase, ready = 4, "Running", "0/1"
            rows.append(
                {
                    "name": f"{name}-{'7d9c8f6b5d' if index % 2 == 0 else '6b5d7d9c8f'}-{replica}",
                    "namespace": namespace,
                    "phase": phase,
                    "ready": ready,
                    "restarts": restarts,
                    "node": "gitops-platform-control-plane",
                    "age": _age(95 + index * 13 + replica * 4),
                    "ip": f"10.244.0.{20 + index * 2 + replica}",
                    "containers": [{"name": name, "ready": ready == "1/1", "restarts": restarts,
                                    "image": f"platform/{name}:1.0.0"}],
                    "owner": f"{name}",
                    "labels": {"app.kubernetes.io/name": name},
                }
            )
    rows.append(
        {
            "name": "postgres-0", "namespace": "platform", "phase": "Running", "ready": "1/1",
            "restarts": 0, "node": "gitops-platform-control-plane", "age": _age(320),
            "ip": "10.244.0.9", "containers": [{"name": "postgres", "ready": True, "restarts": 0,
                                                "image": "postgres:16-alpine"}],
            "owner": "postgres", "labels": {"app.kubernetes.io/name": "postgres"},
        }
    )
    rows.append(
        {
            "name": "reporting-worker-5f8c7d9b6d-x2k4p", "namespace": "platform", "phase": "Failed",
            "ready": "0/1", "restarts": 7, "node": "gitops-platform-control-plane",
            "age": _age(48), "ip": "",
            "containers": [{"name": "worker", "ready": False, "restarts": 7,
                            "image": "platform/reporting-worker:0.9.3"}],
            "owner": "reporting-worker", "labels": {"app.kubernetes.io/name": "reporting-worker"},
        }
    )
    rows.append(
        {
            "name": "load-generator-6d4f9b7c5d-9qzl2", "namespace": "platform", "phase": "Pending",
            "ready": "0/1", "restarts": 0, "node": "", "age": _age(3), "ip": "",
            "containers": [{"name": "k6", "ready": False, "restarts": 0, "image": "grafana/k6:0.52.0"}],
            "owner": "load-generator", "labels": {"app.kubernetes.io/name": "load-generator"},
        }
    )
    return rows


def deployments() -> list[dict]:
    rows = []
    for name, replicas, namespace in SERVICES:
        ready = replicas if name != "order-service" else replicas - 1
        rows.append(
            {
                "name": name,
                "namespace": namespace,
                "desired": replicas,
                "ready": ready,
                "updated": replicas,
                "available": ready,
                "images": [f"platform/{name}:1.0.0"],
                "strategy": "RollingUpdate",
                "age": _age(320 + len(name)),
                "conditions": [
                    {"type": "Available", "status": "True" if ready == replicas else "False"},
                    {"type": "Progressing", "status": "True"},
                ],
            }
        )
    rows.append(
        {"name": "reporting-worker", "namespace": "platform", "desired": 1, "ready": 0,
         "updated": 1, "available": 0, "images": ["platform/reporting-worker:0.9.3"],
         "strategy": "RollingUpdate", "age": _age(48),
         "conditions": [{"type": "Available", "status": "False"}]}
    )
    return rows


def services() -> list[dict]:
    rows = []
    for name, _replicas, namespace in SERVICES:
        port = {
            "api-gateway": 8000, "user-service": 8001, "product-service": 8002,
            "order-service": 8003, "notification-service": 8004, "frontend": 80,
            "platform-api": 8080, "postgres": 5432,
        }[name]
        rows.append(
            {
                "name": name,
                "namespace": namespace,
                "type": "ClusterIP",
                "cluster_ip": "10.96.0." + str(10 + len(rows)),
                "ports": [{"port": port, "target_port": port, "protocol": "TCP", "name": "http"}],
                "selector": {"app.kubernetes.io/name": name},
                "age": _age(320),
            }
        )
    return rows


def workloads() -> list[dict]:
    result = []
    for deployment in deployments():
        result.append(
            {
                "kind": "Deployment",
                "name": deployment["name"],
                "namespace": deployment["namespace"],
                "desired": deployment["desired"],
                "ready": deployment["ready"],
                "images": deployment["images"],
                "age": deployment["age"],
                "status": "Available" if deployment["ready"] == deployment["desired"] else "Degraded",
            }
        )
    result.append({"kind": "StatefulSet", "name": "postgres", "namespace": "platform", "desired": 1,
                   "ready": 1, "images": ["postgres:16-alpine"], "age": _age(320), "status": "Available"})
    result.append({"kind": "DaemonSet", "name": "promtail", "namespace": "logging", "desired": 1,
                   "ready": 1, "images": ["grafana/promtail:3.2.1"], "age": _age(300),
                   "status": "Available"})
    return result


def metrics() -> dict:
    """Deterministic 30-point series so charts are stable between refreshes."""
    now = datetime.now(UTC)
    times = [now - timedelta(minutes=5 * (29 - i)) for i in range(30)]
    cpu = [round(0.18 + 0.10 * math.sin(i / 4) + (i % 5) * 0.006, 3) for i in range(30)]
    memory = [round(0.62 + 0.04 * math.cos(i / 6), 3) for i in range(30)]
    latency = [round(0.045 + 0.02 * abs(math.sin(i / 5)), 3) for i in range(30)]
    rps = [round(9 + 4 * abs(math.sin(i / 3)), 1) for i in range(30)]
    return {
        "series": [
            {"name": "cpu_utilization", "unit": "ratio",
             "points": [{"t": t.isoformat(), "v": v} for t, v in zip(times, cpu, strict=True)]},
            {"name": "memory_utilization", "unit": "ratio",
             "points": [{"t": t.isoformat(), "v": v} for t, v in zip(times, memory, strict=True)]},
            {"name": "http_request_rate", "unit": "req/s",
             "points": [{"t": t.isoformat(), "v": v} for t, v in zip(times, rps, strict=True)]},
            {"name": "http_p95_latency", "unit": "seconds",
             "points": [{"t": t.isoformat(), "v": v} for t, v in zip(times, latency, strict=True)]},
        ],
        "top_pods": [
            {"pod": "prometheus-0", "namespace": "monitoring", "cpu_millicores": 210, "memory_mib": 780},
            {"pod": "api-gateway-7d9c8f6b5d-0", "namespace": "platform", "cpu_millicores": 140,
             "memory_mib": 96},
            {"pod": "order-service-7d9c8f6b5d-0", "namespace": "platform", "cpu_millicores": 95,
             "memory_mib": 88},
            {"pod": "grafana-5c6d7f8b9d-1", "namespace": "monitoring", "cpu_millicores": 60,
             "memory_mib": 210},
        ],
        "summary": {"cpu_millicores": 640, "memory_mib": 2150, "nodes": 1,
                    "pods_measured": 22, "request_rate": 12.4, "error_rate_percent": 0.6,
                    "p95_latency_ms": 62},
    }


def alerts() -> list[dict]:
    now = datetime.now(UTC)
    return [
        {
            "id": "alert-order-restarts", "name": "PodRestartingFrequently", "severity": "warning",
            "status": "firing", "service": "order-service", "namespace": "platform",
            "summary": "order-service restarted 4 times in 15 minutes",
            "description": "Container restarts exceed the 3 restarts/15m threshold.",
            "starts_at": (now - timedelta(minutes=18)).isoformat(),
            "fingerprint": "a1b2c3", "runbook": "docs/TROUBLESHOOTING.md#crashloopbackoff",
        },
        {
            "id": "alert-error-rate", "name": "HighErrorRate", "severity": "warning",
            "status": "firing", "service": "api-gateway", "namespace": "platform",
            "summary": "5xx error ratio above 2% for 10 minutes",
            "description": "http_requests_total{status=~\"5..\"} / total = 3.1% (threshold 2%).",
            "starts_at": (now - timedelta(minutes=11)).isoformat(),
            "fingerprint": "d4e5f6", "runbook": "docs/TROUBLESHOOTING.md#high-error-rate",
        },
    ]


def gitops() -> list[dict]:
    apps = []
    for name, _replicas, _namespace in SERVICES:
        apps.append(
            {
                "name": name,
                "namespace": "argocd",
                "project": "platform",
                "sync_status": "OutOfSync" if name == "order-service" else "Synced",
                "health_status": "Progressing" if name == "order-service" else "Healthy",
                "revision": "9f2c1ab",
                "target_revision": "HEAD",
                "path": f"helm/charts/{name}",
                "destination": "https://kubernetes.default.svc",
                "destination_namespace": "platform",
                "auto_sync": True,
                "last_synced_at": (NOW - timedelta(minutes=7 if name != "order-service" else 41)).isoformat(),
                "message": "Deployment order-service is progressing: 1 of 2 replicas available",
            }
        )
    return apps


def logs() -> list[dict]:
    now = datetime.now(UTC)
    entries = [
        ("api-gateway", "INFO", "request", {"method": "GET", "path": "/api/products", "status": 200,
                                            "duration_ms": 18.4}),
        ("order-service", "ERROR", "upstream_unavailable",
         {"target": "notification-service", "error": "ReadTimeout"}),
        ("order-service", "WARNING", "notification_failed",
         {"order_id": "8f14e45f", "error": "service unavailable"}),
        ("user-service", "INFO", "database_schema_ready", {"attempt": 1}),
        ("product-service", "INFO", "request",
         {"method": "PATCH", "path": "/products/prod-1/stock", "status": 200, "duration_ms": 12.1}),
        ("api-gateway", "ERROR", "api_error", {"code": "dependency_unavailable", "status": 503}),
    ]
    return [
        {
            "timestamp": (now - timedelta(seconds=45 * index)).isoformat(),
            "service": service,
            "level": level,
            "message": message,
            "labels": {"namespace": "platform", "pod": f"{service}-7d9c8f6b5d-0"},
            "fields": fields,
        }
        for index, (service, level, message, fields) in enumerate(entries)
    ]


def security() -> dict:
    return {
        "generated_at": (NOW - timedelta(hours=6)).isoformat(),
        "scanners": ["trivy", "checkov", "kubescape"],
        "summary": {"critical": 0, "high": 2, "medium": 7, "low": 11, "total": 20},
        "findings": [
            {"id": "KSV-0106", "scanner": "kubescape", "severity": "high",
             "resource": "Deployment/frontend", "title": "Container running as root",
             "remediation": "Set runAsNonRoot: true and runAsUser: 10001"},
            {"id": "KSV-0118", "scanner": "kubescape", "severity": "high",
             "resource": "Deployment/platform-api",
             "title": "Container allows privilege escalation",
             "remediation": "Set allowPrivilegeEscalation: false"},
        ],
        "note": "Demo findings shown because no security/findings.json is bundled.",
    }

