# Monitoring and logging

## Components

| Component | Namespace | Port | Purpose |
|---|---|---|---|
| Prometheus | monitoring | 9090 | Metrics store, rule evaluation |
| Alertmanager | monitoring | 9093 | Grouping, inhibition, routing |
| Grafana | monitoring | 3000 | Six provisioned dashboards |
| kube-state-metrics | monitoring | 8080 | Workload/object state |
| node-exporter | monitoring | 9100 | Node CPU, memory, disk, network |
| cAdvisor (kubelet) | kube-system | 10250 | Container resource usage |
| Loki | logging | 3100 | Log store |
| Promtail | logging | 9080 (`DaemonSet`) | Ships pod logs to Loki |

## Metrics exposed by every service

`applications/shared/service_kit/metrics.py`:

- `http_requests_total{service,method,path,status}` — RED signal, path is the route template (bounded cardinality).
- `http_request_duration_seconds_bucket{service,method,path,le}` — p50/p95/p99.
- `http_requests_in_progress`, `service_up`.
- Upstream: `upstream_requests_total{target,outcome}` (success, retry, transport_error, circuit_open, http_5xx), `upstream_request_duration_seconds`.
- Business: `orders_created_total{status}`, `orders_failed_total{reason}`, `order_stock_compensations_total`, `product_stock_reserved_total`, `notifications_sent_total{channel,status}`, `users_created_total`.

## Scraping

In-cluster (`monitoring/prometheus/prometheus.yml`): pod discovery keeps pods annotated `prometheus.io/scrape: "true"`, rewrites the address from `prometheus.io/port`, and labels by namespace/pod/app label. Additional jobs: node-exporter, kube-state-metrics, kubelet cAdvisor.

Compose (`monitoring/prometheus/prometheus.compose.yml`): static targets for the seven containers, used by `docker compose --profile observability`.

Verify:

```powershell
kubectl -n monitoring port-forward svc/prometheus-server 9090:9090
# http://localhost:9090/targets  → every platform pod should be UP
```

## Dashboards

Generated from `tools/generate_dashboards.py` (do not hand-edit JSON):

| Dashboard | UID | Answers |
|---|---|---|
| Cluster Overview | `cluster-overview` | Nodes ready, pod phases, deployments available, CPU/memory, per-namespace usage |
| Node Health | `node-health` | CPU, memory, filesystem, load, disk and network I/O |
| Pod Health | `pod-health` | Restarts, readiness, pods by phase |
| Application Performance | `application-performance` | RPS, 5xx ratio, p50/p95/p99 latency |
| API Latency | `api-latency` | Per-path latency, upstream outcomes, status mix |
| Deployment Monitoring | `deployment-monitoring` | Desired vs available replicas, HPA state |

Regenerate:

```bash
python tools/generate_dashboards.py
kubectl apply -k monitoring      # or docker compose restart grafana
```

## Alerts

`monitoring/prometheus/alert-rules.yml` — every alert has `severity`, `component`, `summary`, `description` and a runbook link into `docs/TROUBLESHOOTING.md`.

| Alert | Expression (summary) | For | Severity |
|---|---|---|---|
| ServiceDown | `up{job="platform-pods"} == 0` | 2m | critical |
| DeploymentUnavailable | available/spec < 0.5 | 5m | critical |
| ApplicationDowntime | no requests recorded | 5m | warning |
| PodCrashLooping | `increase(restarts[15m]) > 3` | 5m | warning |
| PodNotReady | Pending/Unknown phase | 10m | warning |
| HighErrorRate | 5xx ratio > 5% | 5m | critical |
| HighLatencyP95 | p95 > 1s | 5m | warning |
| HighCPUUsage | usage/limit > 85% | 10m | warning |
| HighMemoryUsage | working set/limit > 85% | 10m | warning |
| NodeMemoryPressure | available < 10% | 10m | critical |
| PVCAlmostFull | free < 15% | 10m | warning |

Alertmanager routes by `alertname, service, namespace`, groups critical faster, and inhibits warnings for the same service. The receiver is `ui-only` (no external integration) so the demo works offline; replace it with a webhook when available.

## Logging

Services log one JSON object per line:

```json
{"timestamp":"2026-11-18T09:51:02.418Z","level":"INFO","service":"order-service","environment":"development","logger":"order.workflow","message":"order_created","request_id":"3f1c...","order_id":"8f14e45f","total_cents":13997}
```

Promtail reads `/var/log/pods/*/*.log`, parses JSON, promotes `level` and `service` to labels, and pushes to Loki. Grafana → Explore → Loki:

```logql
{namespace="platform"} | json | level="ERROR"
{app="order-service"} |= "order_created"
sum by (service) (count_over_time({namespace="platform"} | json | level="ERROR" [5m]))
```

Loki retains 168 h with a 2 Gi PVC and compaction enabled.

## Troubleshooting

| Symptom | Check | Fix |
|---|---|---|
| Target `DOWN` | `kubectl -n platform logs deploy/<svc>` | Service not ready → readiness probe failing |
| No application metrics | `curl <pod>:<port>/metrics` | Pod missing `prometheus.io/scrape` annotation |
| Grafana "No data" | datasource URL, time range | `http://prometheus-server.monitoring.svc.cluster.local:9090` |
| HPA `<unknown>` | `kubectl top pods` | metrics-server not ready / no CPU request |
| No logs in Loki | `kubectl -n logging logs ds/promtail` | Promtail cannot read `/var/log/pods` or Loki unreachable |
| Dashboard missing | `kubectl -n monitoring logs deploy/grafana` | Provisioning ConfigMap not mounted |
