"""Generate the Grafana dashboards from one maintained panel catalogue.

Keeping dashboards as code avoids hand-editing large JSON files and guarantees
every dashboard targets the same datasource uid.

Usage: python tools/generate_dashboards.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "monitoring" / "grafana" / "dashboards"
OUT.mkdir(parents=True, exist_ok=True)

DS = {"type": "prometheus", "uid": "prometheus"}


def target(expr: str, legend: str = "", ref: str = "A", instant: bool = False) -> dict:
    return {
        "datasource": DS,
        "expr": expr,
        "legendFormat": legend or expr[:40],
        "refId": ref,
        "instant": instant,
        "range": not instant,
    }


def ts_panel(
    title: str, expr: str, x: int, y: int, w: int = 12, h: int = 8,
    unit: str = "short", legend: str = "", thresholds: list | None = None,
    description: str = "",
) -> dict:
    return {
        "type": "timeseries",
        "title": title,
        "description": description,
        "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {"lineWidth": 2, "fillOpacity": 8, "showPoints": "never"},
                "thresholds": {"mode": "absolute", "steps": thresholds or [{"color": "green", "value": None}]},
            },
            "overrides": [],
        },
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi"},
        },
        "targets": [target(expr, legend)],
    }


def stat_panel(title: str, expr: str, x: int, y: int, w: int = 4, h: int = 4,
               unit: str = "short", color: str = "blue", legend: str = "",
               description: str = "") -> dict:
    return {
        "type": "stat",
        "title": title,
        "description": description,
        "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "color": {"mode": "fixed", "fixedColor": color},
                "thresholds": {"mode": "absolute", "steps": [{"color": color, "value": None}]},
            },
            "overrides": [],
        },
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "colorMode": "value",
            "graphMode": "area",
            "justifyMode": "auto",
            "textMode": "auto",
        },
        "targets": [target(expr, legend, instant=True)],
    }


def table_panel(title: str, expr: str, x: int, y: int, w: int = 12, h: int = 8,
                description: str = "") -> dict:
    return {
        "type": "table",
        "title": title,
        "description": description,
        "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {"custom": {"align": "auto"}}, "overrides": []},
        "options": {"showHeader": True, "cellHeight": "sm"},
        "targets": [target(expr, "", instant=True)],
        "transformations": [{"id": "organize", "options": {"excludeByName": {"Time": True}}}],
    }


def dashboard(uid: str, title: str, panels: list[dict], tags: list[str], description: str) -> dict:
    return {
        "uid": uid,
        "title": title,
        "description": description,
        "tags": ["kubernetes", "gitops-platform", *tags],
        "timezone": "browser",
        "editable": True,
        "schemaVersion": 39,
        "version": 1,
        "refresh": "30s",
        "time": {"from": "now-1h", "to": "now"},
        "templating": {
            "list": [
                {
                    "name": "namespace",
                    "type": "query",
                    "datasource": DS,
                    "query": 'label_values(kube_pod_info, namespace)',
                    "includeAll": True,
                    "multi": True,
                    "refresh": 2,
                    "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
                },
                {
                    "name": "service",
                    "type": "query",
                    "datasource": DS,
                    "query": 'label_values(http_requests_total, service)',
                    "includeAll": True,
                    "multi": True,
                    "refresh": 2,
                    "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
                },
            ]
        },
        "panels": panels,
    }


NS = 'namespace=~"$namespace"'

cluster_overview = dashboard(
    "cluster-overview",
    "Cluster Overview",
    [
        stat_panel("Nodes Ready", 'sum(kube_node_status_condition{condition="Ready",status="true"})',
                   0, 0, unit="short", color="green", description="Nodes reporting Ready"),
        stat_panel("Running Pods", 'sum(kube_pod_status_phase{phase="Running"})', 4, 0,
                   color="blue", description="Pods in Running phase"),
        stat_panel("Failed / Pending", 'sum(kube_pod_status_phase{phase=~"Failed|Pending"})', 8, 0,
                   color="orange", description="Pods that are not scheduling or have failed"),
        stat_panel("Deployments Available",
                   'sum(kube_deployment_status_replicas_available)', 12, 0, color="purple"),
        stat_panel("CPU Utilisation",
                   '1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))', 16, 0,
                   unit="percentunit", color="yellow"),
        stat_panel("Memory Utilisation",
                   "1 - (sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes))",
                   20, 0, unit="percentunit", color="red"),
        ts_panel("Namespace CPU usage (cores)",
                 'sum by (namespace) (rate(container_cpu_usage_seconds_total{container!=""}[5m]))',
                 0, 4, 12, 8, unit="short", legend="{{namespace}}"),
        ts_panel("Namespace memory working set",
                 'sum by (namespace) (container_memory_working_set_bytes{container!=""})',
                 12, 4, 12, 8, unit="bytes", legend="{{namespace}}"),
        table_panel("Deployment replicas",
                    'sum by (namespace, deployment) (kube_deployment_status_replicas_available)',
                    0, 12, 12, 8, description="Available replicas per deployment"),
        table_panel("Pods not running",
                    'sum by (namespace, pod, phase) (kube_pod_status_phase{phase=~"Failed|Pending"}) > 0',
                    12, 12, 12, 8),
    ],
    ["cluster", "overview"],
    "Golden-signal overview of the local Kind cluster and platform workloads.",
)

node_health = dashboard(
    "node-health",
    "Node Health",
    [
        stat_panel("Node CPU", '1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))', 0, 0,
                   unit="percentunit", color="yellow"),
        stat_panel("Node Memory",
                   "1 - (sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes))",
                   4, 0, unit="percentunit", color="red"),
        stat_panel("Filesystem Used",
                   "1 - (sum(node_filesystem_avail_bytes{fstype!~\"tmpfs|overlay\"}) "
                   "/ sum(node_filesystem_size_bytes{fstype!~\"tmpfs|overlay\"}))",
                   8, 0, unit="percentunit", color="orange"),
        stat_panel("Load (1m)", "node_load1", 12, 0, color="blue"),
        ts_panel("CPU by node", 'avg by (node) (1 - rate(node_cpu_seconds_total{mode="idle"}[5m]))',
                 0, 4, 12, 8, unit="percentunit", legend="{{node}}"),
        ts_panel("Memory available by node",
                 "node_memory_MemAvailable_bytes", 12, 4, 12, 8, unit="bytes", legend="{{node}}"),
        ts_panel("Disk I/O read", "rate(node_disk_read_bytes_total[5m])", 0, 12, 12, 8,
                 unit="Bps", legend="{{device}}"),
        ts_panel("Network receive", "rate(node_network_receive_bytes_total[5m])", 12, 12, 12, 8,
                 unit="Bps", legend="{{device}}"),
    ],
    ["node"],
    "Node-level capacity and saturation for the Kind node running the platform.",
)

pod_health = dashboard(
    "pod-health",
    "Pod Health",
    [
        stat_panel("Running", 'sum(kube_pod_status_phase{phase="Running"})', 0, 0, color="green"),
        stat_panel("Pending", 'sum(kube_pod_status_phase{phase="Pending"})', 4, 0, color="orange"),
        stat_panel("Failed", 'sum(kube_pod_status_phase{phase="Failed"})', 8, 0, color="red"),
        stat_panel("Restarts (15m)",
                   "sum(increase(kube_pod_container_status_restarts_total[15m]))", 12, 0,
                   color="purple"),
        ts_panel("Restarts by pod",
                 "sum by (namespace, pod) (increase(kube_pod_container_status_restarts_total[15m]))",
                 0, 4, 12, 8, legend="{{namespace}}/{{pod}}",
                 thresholds=[{"color": "green", "value": None},
                             {"color": "orange", "value": 1},
                             {"color": "red", "value": 3}]),
        ts_panel("Ready containers",
                 'sum by (namespace, pod) (kube_pod_container_status_ready)',
                 12, 4, 12, 8, legend="{{namespace}}/{{pod}}"),
        table_panel("Pod restarts total",
                    "sum by (namespace, pod, container) (kube_pod_container_status_restarts_total) > 0",
                    0, 12, 12, 8),
        table_panel("Pods by phase",
                    "sum by (namespace, phase) (kube_pod_status_phase) > 0", 12, 12, 12, 8),
    ],
    ["pods"],
    "Pod lifecycle, readiness and restart signal used for crash-loop alerting.",
)

app_performance = dashboard(
    "application-performance",
    "Application Performance",
    [
        stat_panel("Request rate", "sum(rate(http_requests_total[5m]))", 0, 0, unit="reqps",
                   color="blue"),
        stat_panel("5xx ratio",
                   'sum(rate(http_requests_total{status=~"5.."}[5m])) '
                   "/ clamp_min(sum(rate(http_requests_total[5m])), 0.001)",
                   4, 0, unit="percentunit", color="red"),
        stat_panel("p95 latency",
                   "histogram_quantile(0.95, sum by (le) "
                   "(rate(http_request_duration_seconds_bucket[5m])))",
                   8, 0, unit="s", color="orange"),
        stat_panel("Uptime (targets up)",
                   'sum(up{job="platform-pods"})', 12, 0, color="green"),
        ts_panel("Requests per second by service",
                 "sum by (service) (rate(http_requests_total[5m]))", 0, 4, 12, 8,
                 unit="reqps", legend="{{service}}"),
        ts_panel("5xx error ratio by service",
                 'sum by (service) (rate(http_requests_total{status=~"5.."}[5m])) '
                 "/ clamp_min(sum by (service) (rate(http_requests_total[5m])), 0.001)",
                 12, 4, 12, 8, unit="percentunit", legend="{{service}}",
                 thresholds=[{"color": "green", "value": None},
                             {"color": "orange", "value": 0.02},
                             {"color": "red", "value": 0.05}]),
        ts_panel("Latency p50 / p95 / p99",
                 "histogram_quantile(0.5, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))",
                 0, 12, 24, 8, unit="s", legend="p50"),
    ],
    ["application"],
    "HTTP golden signals collected from the FastAPI services' /metrics endpoints.",
)

# Second query on the latency panel for p95/p99.
app_performance["panels"][6]["targets"] = [
    target("histogram_quantile(0.5, sum by (le) "
           "(rate(http_request_duration_seconds_bucket[5m])))", "p50", "A"),
    target("histogram_quantile(0.95, sum by (le) "
           "(rate(http_request_duration_seconds_bucket[5m])))", "p95", "B"),
    target("histogram_quantile(0.99, sum by (le) "
           "(rate(http_request_duration_seconds_bucket[5m])))", "p99", "C"),
]

api_latency = dashboard(
    "api-latency",
    "API Latency",
    [
        stat_panel("Gateway p95",
                   'histogram_quantile(0.95, sum by (le) '
                   '(rate(http_request_duration_seconds_bucket{service="api-gateway"}[5m])))',
                   0, 0, unit="s", color="orange"),
        stat_panel("Gateway RPS", 'sum(rate(http_requests_total{service="api-gateway"}[5m]))',
                   4, 0, unit="reqps", color="blue"),
        stat_panel("Gateway 4xx", 'sum(rate(http_requests_total{service="api-gateway",status=~"4.."}[5m]))',
                   8, 0, unit="reqps", color="yellow"),
        stat_panel("Gateway 5xx", 'sum(rate(http_requests_total{service="api-gateway",status=~"5.."}[5m]))',
                   12, 0, unit="reqps", color="red"),
        ts_panel("Latency by path (p95)",
                 "histogram_quantile(0.95, sum by (le, path) "
                 "(rate(http_request_duration_seconds_bucket[5m])))",
                 0, 4, 24, 9, unit="s", legend="{{path}}"),
        ts_panel("Upstream calls by target and outcome",
                 "sum by (target, outcome) (rate(upstream_requests_total[5m]))",
                 0, 13, 12, 8, unit="reqps", legend="{{target}} {{outcome}}"),
        ts_panel("Requests by status class",
                 "sum by (status) (rate(http_requests_total[5m]))",
                 12, 13, 12, 8, unit="reqps", legend="{{status}}"),
    ],
    ["latency", "api"],
    "Request-level latency and upstream reliability across the gateway and services.",
)

deployment_monitoring = dashboard(
    "deployment-monitoring",
    "Deployment Monitoring",
    [
        stat_panel("Deployments", "count(kube_deployment_spec_replicas)", 0, 0, color="blue"),
        stat_panel("Fully available",
                   "count(kube_deployment_status_replicas_available "
                   "== bool on(deployment, namespace) kube_deployment_spec_replicas)",
                   4, 0, color="green"),
        stat_panel("Progressing",
                   'sum(kube_deployment_status_condition{condition="Progressing",status="true"})',
                   8, 0, color="orange"),
        stat_panel("HPA current replicas",
                   "sum(kube_horizontalpodautoscaler_status_current_replicas)", 12, 0, color="purple"),
        ts_panel("Desired vs available replicas",
                 "sum by (deployment) (kube_deployment_spec_replicas)", 0, 4, 12, 8,
                 legend="{{deployment}} desired"),
        ts_panel("HPA replicas over time",
                 "kube_horizontalpodautoscaler_status_current_replicas",
                 12, 4, 12, 8, legend="{{horizontalpodautoscaler}}"),
        table_panel("Deployment availability",
                    "kube_deployment_status_replicas_available", 0, 12, 12, 8),
        table_panel("HPA targets",
                    "kube_horizontalpodautoscaler_status_target_metric", 12, 12, 12, 8),
    ],
    ["deployments", "hpa"],
    "Rollout health, replica availability and autoscaler state.",
)

for item in (cluster_overview, node_health, pod_health, app_performance, api_latency, deployment_monitoring):
    path = OUT / f"{item['uid']}.json"
    path.write_text(json.dumps(item, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(OUT.parents[2])} ({len(item['panels'])} panels)")
