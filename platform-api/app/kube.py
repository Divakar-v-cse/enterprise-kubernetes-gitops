"""Read-only Kubernetes/observability collectors.

The platform API uses a dedicated read-only ServiceAccount (see
kubernetes/base/platform-api-rbac.yaml) and never mutates cluster state.
Every method degrades to a clearly-labelled demo payload when the cluster or a
monitoring backend is unreachable.
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from . import demo
from .config import settings

CPU_SUFFIX = {"n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3}


def parse_cpu(value: str | None) -> float:
    if not value:
        return 0.0
    value = str(value)
    for suffix in ("n", "u", "m", ""):
        if value.endswith(suffix) and suffix:
            try:
                return float(value[: -len(suffix)]) * CPU_SUFFIX[suffix]
            except ValueError:
                return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def parse_memory_mib(value: str | None) -> float:
    if not value:
        return 0.0
    value = str(value)
    units = {"Ki": 1 / 1024, "Mi": 1.0, "Gi": 1024.0, "K": 1 / 1024, "M": 1.0, "G": 1024.0}
    for suffix, factor in units.items():
        if value.endswith(suffix):
            try:
                return float(value[: -len(suffix)]) * factor
            except ValueError:
                return 0.0
    try:
        return float(value) / (1024 * 1024)
    except ValueError:
        return 0.0


def age_of(timestamp: datetime | None) -> str:
    if timestamp is None:
        return "unknown"
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - timestamp
    seconds = int(delta.total_seconds())
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d{hours}h"
    if hours:
        return f"{hours}h{minutes}m"
    return f"{minutes}m"


class ClusterAccess:
    """Lazy, cached, read-only access to the Kubernetes API."""

    def __init__(self) -> None:
        self.available = False
        self.error: str | None = None
        self.core: client.CoreV1Api | None = None
        self.apps: client.AppsV1Api | None = None
        self.custom: client.CustomObjectsApi | None = None
        self._cache: dict[str, tuple[float, Any]] = {}
        self._last_attempt = 0.0

    # -- connection -----------------------------------------------------
    def connect(self, force: bool = False) -> bool:
        if self.available and not force:
            return True
        if not force and time.monotonic() - self._last_attempt < 10:
            return self.available
        self._last_attempt = time.monotonic()
        if settings.demo_mode:
            self.available = False
            self.error = "PLATFORM_DEMO_MODE=true"
            return False
        try:
            if settings.in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config(context=settings.kube_context)
            self.core = client.CoreV1Api()
            self.apps = client.AppsV1Api()
            self.custom = client.CustomObjectsApi()
            self.core.list_namespace(limit=1, _request_timeout=4)
            self.available = True
            self.error = None
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            self.available = False
            self.error = str(exc)[:300]
        return self.available

    def cached(self, key: str, fn: Callable[[], Any]) -> Any:
        ttl = settings.cache_ttl_seconds
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
        value = fn()
        self._cache[key] = (time.monotonic(), value)
        return value

    # -- collectors -----------------------------------------------------
    def overview(self) -> dict:
        def collect() -> dict:
            assert self.core and self.apps
            nodes = self.core.list_node(_request_timeout=6).items
            pods = self.core.list_pod_for_all_namespaces(_request_timeout=8).items
            deployments = self.apps.list_deployment_for_all_namespaces(_request_timeout=8).items
            namespaces = self.core.list_namespace(_request_timeout=6).items

            ready_nodes = 0
            cpu_capacity = 0.0
            mem_capacity = 0.0
            for node in nodes:
                for condition in node.status.conditions or []:
                    if condition.type == "Ready" and condition.status == "True":
                        ready_nodes += 1
                cpu_capacity += parse_cpu((node.status.capacity or {}).get("cpu"))
                mem_capacity += parse_memory_mib((node.status.capacity or {}).get("memory")) / 1024

            phases = {"Running": 0, "Pending": 0, "Failed": 0, "Succeeded": 0}
            for pod in pods:
                phase = pod.status.phase or "Unknown"
                phases[phase] = phases.get(phase, 0) + 1
            available = sum(1 for d in deployments if (d.status.available_replicas or 0) > 0)

            usage_cpu = 0.0
            usage_mem = 0.0
            try:
                node_metrics = self.custom.list_cluster_custom_object(
                    "metrics.k8s.io", "v1beta1", "nodes", _request_timeout=6
                )
                for item in node_metrics.get("items", []):
                    usage_cpu += parse_cpu(item["usage"].get("cpu"))
                    usage_mem += parse_memory_mib(item["usage"].get("memory"))
            except Exception:  # metrics-server unavailable
                pass

            version = self.core.api_client.configuration.host  # noqa: F841 - keep host for debug
            try:
                server_version = client.VersionApi().get_code(_request_timeout=4).git_version
            except Exception:
                server_version = "unknown"

            return {
                "cluster": {
                    "name": settings.cluster_name,
                    "version": server_version,
                    "provider": "in-cluster" if settings.in_cluster else "local kubeconfig",
                    "status": "Ready" if ready_nodes == len(nodes) and nodes else "Degraded",
                    "created_at": None,
                },
                "nodes": {
                    "total": len(nodes), "ready": ready_nodes,
                    "cpu_capacity_cores": round(cpu_capacity, 2),
                    "memory_capacity_gib": round(mem_capacity, 2),
                },
                "pods": {
                    "total": len(pods), "running": phases.get("Running", 0),
                    "pending": phases.get("Pending", 0), "failed": phases.get("Failed", 0),
                    "succeeded": phases.get("Succeeded", 0),
                },
                "deployments": {
                    "total": len(deployments), "available": available,
                    "unavailable": len(deployments) - available,
                },
                "namespaces": len(namespaces),
                "pods_by_namespace": _pods_by_namespace(pods),
                "resource_usage": {
                    "cpu_millicores": round(usage_cpu * 1000),
                    "memory_mib": round(usage_mem),
                    "cpu_percent": round(usage_cpu / cpu_capacity * 100, 1) if cpu_capacity else 0,
                    "memory_percent": round(usage_mem / (mem_capacity * 1024) * 100, 1)
                    if mem_capacity else 0,
                },
                "alerts": {"firing": 0, "critical": 0},
                "gitops": {"applications": 0, "synced": 0, "out_of_sync": 0, "degraded": 0},
                "throughput_rps": 0,
                "error_rate_percent": 0,
            }

        return self.cached("overview", collect)

    def namespaces(self) -> list[dict]:
        def collect() -> list[dict]:
            assert self.core
            pods = self.core.list_pod_for_all_namespaces(_request_timeout=8).items
            counts = _pods_by_namespace(pods)
            return [
                {
                    "name": ns.metadata.name,
                    "status": ns.status.phase,
                    "pods": counts.get(ns.metadata.name, 0),
                    "labels": ns.metadata.labels or {},
                    "age": age_of(ns.metadata.creation_timestamp),
                }
                for ns in self.core.list_namespace(_request_timeout=6).items
            ]

        return self.cached("namespaces", collect)

    def pods(self) -> list[dict]:
        def collect() -> list[dict]:
            assert self.core
            rows = []
            for pod in self.core.list_pod_for_all_namespaces(_request_timeout=8).items:
                statuses = pod.status.container_statuses or []
                ready = sum(1 for s in statuses if s.ready)
                restarts = sum(s.restart_count or 0 for s in statuses)
                rows.append(
                    {
                        "name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "phase": pod.status.phase,
                        "ready": f"{ready}/{len(pod.spec.containers or [])}",
                        "restarts": restarts,
                        "node": pod.spec.node_name or "",
                        "age": age_of(pod.metadata.creation_timestamp),
                        "ip": pod.status.pod_ip or "",
                        "containers": [
                            {
                                "name": s.name, "ready": s.ready,
                                "restarts": s.restart_count or 0,
                                "image": s.image,
                            }
                            for s in statuses
                        ],
                        "owner": (pod.metadata.owner_references[0].name
                                  if pod.metadata.owner_references else ""),
                        "labels": pod.metadata.labels or {},
                    }
                )
            return rows

        return self.cached("pods", collect)

    def deployments(self) -> list[dict]:
        def collect() -> list[dict]:
            assert self.apps
            rows = []
            for d in self.apps.list_deployment_for_all_namespaces(_request_timeout=8).items:
                containers = (d.spec.template.spec.containers or [])
                rows.append(
                    {
                        "name": d.metadata.name,
                        "namespace": d.metadata.namespace,
                        "desired": d.spec.replicas or 0,
                        "ready": d.status.ready_replicas or 0,
                        "updated": d.status.updated_replicas or 0,
                        "available": d.status.available_replicas or 0,
                        "images": [c.image for c in containers],
                        "strategy": (d.spec.strategy.type if d.spec.strategy else "RollingUpdate"),
                        "age": age_of(d.metadata.creation_timestamp),
                        "conditions": [
                            {"type": c.type, "status": c.status}
                            for c in (d.status.conditions or [])
                        ],
                    }
                )
            return rows

        return self.cached("deployments", collect)

    def workloads(self) -> list[dict]:
        rows = [
            {
                "kind": "Deployment", "name": d["name"], "namespace": d["namespace"],
                "desired": d["desired"], "ready": d["ready"], "images": d["images"],
                "age": d["age"],
                "status": "Available" if d["ready"] >= d["desired"] and d["desired"] else "Degraded",
            }
            for d in self.deployments()
        ]
        def collect_sets() -> list[dict]:
            assert self.apps
            extra: list[dict] = []
            for sts in self.apps.list_stateful_set_for_all_namespaces(_request_timeout=8).items:
                extra.append({
                    "kind": "StatefulSet", "name": sts.metadata.name,
                    "namespace": sts.metadata.namespace, "desired": sts.spec.replicas or 0,
                    "ready": sts.status.ready_replicas or 0,
                    "images": [c.image for c in sts.spec.template.spec.containers],
                    "age": age_of(sts.metadata.creation_timestamp),
                    "status": "Available" if (sts.status.ready_replicas or 0) == (sts.spec.replicas or 0)
                    else "Degraded",
                })
            for ds in self.apps.list_daemon_set_for_all_namespaces(_request_timeout=8).items:
                extra.append({
                    "kind": "DaemonSet", "name": ds.metadata.name,
                    "namespace": ds.metadata.namespace, "desired": ds.status.desired_number_scheduled or 0,
                    "ready": ds.status.number_ready or 0,
                    "images": [c.image for c in ds.spec.template.spec.containers],
                    "age": age_of(ds.metadata.creation_timestamp),
                    "status": "Available"
                    if (ds.status.number_ready or 0) == (ds.status.desired_number_scheduled or 0)
                    else "Degraded",
                })
            return extra

        return rows + self.cached("workload_sets", collect_sets)

    def services(self) -> list[dict]:
        def collect() -> list[dict]:
            assert self.core
            return [
                {
                    "name": svc.metadata.name,
                    "namespace": svc.metadata.namespace,
                    "type": svc.spec.type,
                    "cluster_ip": svc.spec.cluster_ip,
                    "ports": [
                        {"port": p.port, "target_port": p.target_port, "protocol": p.protocol,
                         "name": p.name or "http"}
                        for p in (svc.spec.ports or [])
                    ],
                    "selector": svc.spec.selector or {},
                    "age": age_of(svc.metadata.creation_timestamp),
                }
                for svc in self.core.list_service_for_all_namespaces(_request_timeout=8).items
            ]

        return self.cached("services", collect)

    # -- observability --------------------------------------------------
    def metrics(self) -> dict:
        def collect() -> dict:
            top_pods = []
            try:
                assert self.custom
                pod_metrics = self.custom.list_cluster_custom_object(
                    "metrics.k8s.io", "v1beta1", "pods", _request_timeout=6
                )
                for item in pod_metrics.get("items", []):
                    cpu = sum(parse_cpu(c["usage"].get("cpu")) for c in item.get("containers", []))
                    mem = sum(parse_memory_mib(c["usage"].get("memory")) for c in item.get("containers", []))
                    top_pods.append({
                        "pod": item["metadata"]["name"],
                        "namespace": item["metadata"]["namespace"],
                        "cpu_millicores": round(cpu * 1000),
                        "memory_mib": round(mem),
                    })
                top_pods.sort(key=lambda p: p["cpu_millicores"], reverse=True)
                top_pods = top_pods[:10]
            except Exception:
                top_pods = []

            series = _prometheus_series()
            summary = {
                "cpu_millicores": sum(p["cpu_millicores"] for p in top_pods),
                "memory_mib": sum(p["memory_mib"] for p in top_pods),
                "nodes": self.overview()["nodes"]["total"],
                "pods_measured": len(top_pods),
                "request_rate": _last_value(series, "http_request_rate"),
                "error_rate_percent": _last_value(series, "error_rate"),
                "p95_latency_ms": round(_last_value(series, "http_p95_latency") * 1000, 1),
            }
            return {"series": series, "top_pods": top_pods, "summary": summary}

        return self.cached("metrics", collect)

    def alerts(self) -> list[dict]:
        try:
            with httpx.Client(timeout=settings.request_timeout_seconds) as http:
                response = http.get(f"{settings.alertmanager_url}/api/v2/alerts")
                response.raise_for_status()
                rows = []
                for alert in response.json():
                    labels = alert.get("labels", {})
                    annotations = alert.get("annotations", {})
                    rows.append({
                        "id": alert.get("fingerprint", ""),
                        "name": labels.get("alertname", "unknown"),
                        "severity": labels.get("severity", "warning"),
                        "status": (alert.get("status") or {}).get("state", "active"),
                        "service": labels.get("service", labels.get("job", "platform")),
                        "namespace": labels.get("namespace", ""),
                        "summary": annotations.get("summary", ""),
                        "description": annotations.get("description", ""),
                        "starts_at": alert.get("startsAt"),
                        "fingerprint": alert.get("fingerprint", ""),
                        "runbook": annotations.get("runbook", "docs/TROUBLESHOOTING.md"),
                    })
                return rows
        except Exception:
            return []

    def gitops(self) -> list[dict]:
        def collect() -> list[dict]:
            assert self.custom
            result = self.custom.list_namespaced_custom_object(
                "argoproj.io", "v1alpha1", settings.argocd_namespace, "applications",
                _request_timeout=6,
            )
            rows = []
            for app in result.get("items", []):
                status = app.get("status", {})
                spec = app.get("spec", {})
                sync = status.get("sync", {})
                health = status.get("health", {})
                source = (spec.get("sources") or [spec.get("source", {})])[0]
                rows.append({
                    "name": app["metadata"]["name"],
                    "namespace": app["metadata"]["namespace"],
                    "project": spec.get("project", "default"),
                    "sync_status": sync.get("status", "Unknown"),
                    "health_status": health.get("status", "Unknown"),
                    "revision": (sync.get("revision") or "")[:7],
                    "target_revision": source.get("targetRevision", "HEAD"),
                    "path": source.get("path", ""),
                    "destination": (spec.get("destination") or {}).get("server", ""),
                    "destination_namespace": (spec.get("destination") or {}).get("namespace", ""),
                    "auto_sync": bool((spec.get("syncPolicy") or {}).get("automated")),
                    "last_synced_at": (status.get("operationState") or {}).get("finishedAt"),
                    "message": health.get("message") or (sync.get("comparedTo") and "compared")
                    or "",
                })
            return rows

        return self.cached("gitops", collect)

    def security(self) -> dict:
        path = Path(settings.security_findings_path)
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["note"] = "Generated by the security scan pipeline."
                return payload
            except Exception as exc:
                return {"generated_at": None, "scanners": [], "summary": {}, "findings": [],
                        "note": f"findings file unreadable: {exc}"}
        return demo.security()

    def logs(self, namespace: str | None, pod: str | None, level: str | None, limit: int) -> list[dict]:
        entries = _loki_logs(namespace, pod, level, limit)
        if entries is not None:
            return entries
        if not (self.available and self.core):
            raise RuntimeError("cluster unavailable")
        if not pod:
            raise ValueError("pod is required when Loki is unavailable")
        assert self.core
        raw = self.core.read_namespaced_pod_log(
            name=pod, namespace=namespace or "default", tail_lines=limit, timestamps=True,
            _request_timeout=8,
        )
        rows = []
        for line in raw.splitlines()[-limit:]:
            timestamp, _, message = line.partition(" ")
            try:
                fields = json.loads(message)
            except ValueError:
                fields = {"message": message}
            if level and str(fields.get("level", "")).lower() != level.lower():
                continue
            rows.append({
                "timestamp": timestamp,
                "service": fields.get("service", pod),
                "level": fields.get("level", "INFO"),
                "message": fields.get("message", message),
                "labels": {"namespace": namespace or "default", "pod": pod},
                "fields": {k: v for k, v in fields.items()
                           if k not in {"timestamp", "level", "service", "message"}},
            })
        return rows


def _pods_by_namespace(pods) -> dict[str, int]:
    counts: dict[str, int] = {}
    for pod in pods:
        ns = pod.metadata.namespace
        counts[ns] = counts.get(ns, 0) + 1
    return counts


def _prom_query(query: str) -> list[dict]:
    with httpx.Client(timeout=settings.request_timeout_seconds) as http:
        response = http.get(f"{settings.prometheus_url}/api/v1/query", params={"query": query})
        response.raise_for_status()
        return response.json().get("data", {}).get("result", [])


def _prom_range(query: str, minutes: int = 150) -> list[dict]:
    end = time.time()
    with httpx.Client(timeout=settings.request_timeout_seconds) as http:
        response = http.get(
            f"{settings.prometheus_url}/api/v1/query_range",
            params={"query": query, "start": end - minutes * 60, "end": end, "step": "300"},
        )
        response.raise_for_status()
        result = response.json().get("data", {}).get("result", [])
        if not result:
            return []
        return [
            {"t": datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat(), "v": round(float(val), 4)}
            for ts, val in result[0].get("values", [])
        ]


def _prometheus_series() -> list[dict]:
    queries = {
        "cpu_utilization": '1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))',
        "memory_utilization": "1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)",
        "http_request_rate": "sum(rate(http_requests_total[5m]))",
        "http_p95_latency": (
            "histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))"
        ),
        "error_rate": (
            'sum(rate(http_requests_total{status=~"5.."}[5m])) / '
            "clamp_min(sum(rate(http_requests_total[5m])), 0.001)"
        ),
    }
    series = []
    try:
        for name, query in queries.items():
            points = _prom_range(query)
            if points:
                series.append({"name": name, "unit": _unit_for(name), "points": points})
    except Exception:
        return []
    return series


def _unit_for(name: str) -> str:
    return {
        "cpu_utilization": "ratio", "memory_utilization": "ratio",
        "http_request_rate": "req/s", "http_p95_latency": "seconds", "error_rate": "ratio",
    }.get(name, "")


def _last_value(series: list[dict], name: str) -> float:
    for item in series:
        if item["name"] == name and item["points"]:
            return float(item["points"][-1]["v"])
    return 0.0


def _loki_logs(namespace: str | None, pod: str | None, level: str | None, limit: int) -> list[dict] | None:
    selectors = ['{namespace="%s"}' % namespace] if namespace else ['{namespace=~".+"}']
    if pod:
        selectors = ['{pod="%s"}' % pod]
    if level:
        selectors.append(f'| json | level="{level.upper()}"')
    query = " ".join(selectors)
    try:
        with httpx.Client(timeout=settings.request_timeout_seconds) as http:
            response = http.get(
                f"{settings.loki_url}/loki/api/v1/query_range",
                params={"query": query, "limit": limit, "direction": "backward"},
            )
            response.raise_for_status()
            streams = response.json().get("data", {}).get("result", [])
            rows = []
            for stream in streams:
                labels = stream.get("stream", {})
                for ts, line in stream.get("values", []):
                    try:
                        fields = json.loads(line)
                    except ValueError:
                        fields = {"message": line}
                    rows.append({
                        "timestamp": datetime.fromtimestamp(int(ts) / 1e9, tz=timezone.utc).isoformat(),
                        "service": fields.get("service", labels.get("app", "unknown")),
                        "level": fields.get("level", "INFO"),
                        "message": fields.get("message", line),
                        "labels": labels,
                        "fields": {k: v for k, v in fields.items()
                                   if k not in {"timestamp", "level", "service", "message"}},
                    })
            rows.sort(key=lambda r: r["timestamp"], reverse=True)
            return rows[:limit]
    except Exception:
        return None


cluster = ClusterAccess()
