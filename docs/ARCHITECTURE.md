# Architecture

## 1. Goals and constraints

The platform must demonstrate real container orchestration, automated deployment, observability and reliability engineering **without paid infrastructure**. Every component therefore runs locally: Kind for the cluster, Docker Compose for the fast path, and in-cluster Prometheus/Grafana/Alertmanager/Loki.

Non-goals: multi-region failover, managed cloud services, TLS certificate automation, external identity providers.

## 2. Logical architecture

![Architecture](architecture.png)

Editable source: [`architecture.mmd`](architecture.mmd).

Four planes:

| Plane | Components | Responsibility |
|---|---|---|
| Edge | NGINX Ingress, api-gateway, frontend | TLS termination point, public contract, auth, rate limiting |
| Domain | user, product, order, notification services | Business capabilities, one database per context |
| Platform | platform-api, Argo CD, kube-state-metrics | Read-only operational data, desired-state reconciliation |
| Observability | Prometheus, Alertmanager, Grafana, Loki, Promtail | Metrics, alerting, dashboards, logs |

## 3. Services

| Service | Port | Data store | Key behaviour |
|---|---|---|---|
| api-gateway | 8000 | — | API-key auth for writes, 240 req/min per client, fan-out health, catalog aggregation, circuit breaker per upstream |
| user-service | 8001 | `users` | Email uniqueness, pagination, tier field |
| product-service | 8002 | `products` | Conditional `UPDATE ... WHERE stock >= n` prevents oversell |
| order-service | 8003 | `orders` | Saga: validate user → price basket → reserve stock → persist → notify |
| notification-service | 8004 | `notifications` | Idempotent per (order, subject), retry endpoint, simulated provider |
| frontend | 8080 (80) | — | React 18 SPA, 14 ops pages + storefront |
| platform-api | 8080 | — | 12 read-only endpoints, bearer auth, demo fallback labelled |

### Order saga

```
POST /api/orders
  ├─ user-service      GET /users/{id}           404 → 422 unknown_user
  ├─ product-service   GET /products/{id}        404 → 422 unknown_product
  ├─ product-service   PATCH /products/{id}/stock {delta:-qty}
  │      409 → compensate all previous reservations, return 409
  ├─ orders DB         INSERT order + items
  └─ notification-service POST /notifications    failure → status notification_pending
```

Compensation is best-effort and logged; a failed release increments `order_stock_compensations_total` so it is visible in Grafana rather than silently lost.

### Resilience primitives

`applications/shared/service_kit/http.py`:

- **Timeouts** — 2.5 s per attempt (`REQUEST_TIMEOUT_SECONDS`).
- **Retries** — 2 retries on transport errors and 429/5xx, exponential backoff with jitter.
- **Circuit breaker** — 5 consecutive failures per target opens the circuit for 15 s, then half-opens.
- **Observability** — `upstream_requests_total{target,outcome}` and latency histogram.

## 4. Data model

One PostgreSQL instance, four databases (`users`, `products`, `orders`, `notifications`) created by an init ConfigMap. This keeps local resource use low while preserving bounded contexts; splitting into four servers is a deployment change, not a code change.

`orders` and `order_items` use a cascade delete, and `orders.idempotency_key` is unique so a retried client request cannot double-reserve stock.

## 5. Kubernetes topology

```
namespace platform            namespace monitoring      namespace logging
  postgres (StatefulSet, PVC)   prometheus                loki (StatefulSet, PVC)
  api-gateway  x2               alertmanager              promtail (DaemonSet)
  user-service x2               grafana
  product-service x2            kube-state-metrics
  order-service x2              node-exporter (DaemonSet)
  notification-service x2
  frontend x2
  platform-api x1 (+ read-only ClusterRole)
```

- **Probes**: startup (`/health/live`, 30 × 3 s), readiness (`/health/ready`), liveness (`/health/live`).
- **Security context**: `runAsNonRoot`, UID 10001 (101 for NGINX, 65534 for exporters), `allowPrivilegeEscalation: false`, all capabilities dropped, `RuntimeDefault` seccomp, read-only root filesystem with an `emptyDir` at `/tmp`.
- **Disruption**: PDB `minAvailable: 1` per service; rolling updates use `maxSurge: 1, maxUnavailable: 0`.
- **Scaling**: HPA on api-gateway (65% CPU, 1-3 dev), order-service and product-service (70% CPU).
- **Network**: default-deny both directions; allow-lists for ingress-controller → edge, gateway → services, order-service → dependencies, services → postgres, monitoring → metrics ports, and DNS.

## 6. GitOps model

```
developer → PR → CI (test, build, scan) → merge → image tag in Git → Argo CD compares
   → development auto-sync (prune + selfHeal) → health check
   → production Application stays OutOfSync until a human syncs
```

Argo CD never receives cluster-admin credentials from CI; CI only writes Git. The dashboard never receives cluster-admin either: `platform-api` runs with a `ClusterRole` limited to `get`/`list` on workloads, nodes, namespaces and Argo `Application` objects — no secrets, no writes.

## 7. Observability design

| Signal | Source | Destination |
|---|---|---|
| HTTP golden signals | `service_kit/metrics.py` on every service | Prometheus → Grafana |
| Workload state | kube-state-metrics | Prometheus → alerts |
| Node saturation | node-exporter, cAdvisor | Prometheus → Grafana |
| Upstream health | `upstream_requests_total`, circuit logs | Grafana, Alerts |
| Logs | JSON stdout → Promtail → Loki | Grafana Explore |
| Alerts | `monitoring/prometheus/alert-rules.yml` | Alertmanager (UI-only receiver) |

## 8. Trade-offs

1. **Single node** — cheapest reproducible target; production overlay is rendered and validated but not fully scheduled on 3 GB.
2. **Shared PostgreSQL** — four databases, one server: fewer moving parts locally, same schema isolation.
3. **In-cluster demo fallback** — the platform API returns demo data when the cluster is unreachable, but always with `meta.source=demo` so the UI can never present it as live.
4. **Generated charts** — one hardened chart plus a generator, instead of six hand-maintained copies; drift is impossible and each release stays self-contained.
