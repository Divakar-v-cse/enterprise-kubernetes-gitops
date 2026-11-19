# Enterprise Kubernetes GitOps Platform

Production-shaped reference platform for running a microservices application on Kubernetes with GitOps delivery, full observability, autoscaling and security guardrails — built to run end-to-end on a laptop at zero cost.

![Architecture](docs/architecture.png)

## What this project demonstrates

| Capability | Implementation |
|---|---|
| Microservices | 5 FastAPI services + React/TypeScript dashboard, each independently deployable |
| Service-to-service resilience | Timeouts, bounded retries, per-target circuit breaker, saga compensation |
| Containers | Multi-stage builds, non-root (UID 10001), read-only root FS, health checks |
| Orchestration | Kind cluster, 3 probes per container, PDBs, HPA, rolling updates |
| Packaging | One reusable Helm chart rendered into 6 self-contained service charts |
| GitOps | Argo CD app-of-apps, sync waves, self-heal, manual production gate |
| Observability | Prometheus, 6 Grafana dashboards, Alertmanager rules, Loki + Promtail logs |
| Security | NetworkPolicies (default deny), read-only RBAC, Pod Security Standards, Trivy/Checkov/Bandit/pip-audit |
| CI/CD | GitHub Actions (test, build, scan, validate) + equivalent Jenkinsfile |
| Operations UI | 14-page React dashboard reading a read-only platform API, with explicit demo fallback |

## Application architecture

```
Browser ──► NGINX Ingress (localhost:18080)
              ├── /            → frontend (React SPA)
              ├── /platform    → platform-api (read-only cluster data)
              └── /gateway     → api-gateway
                                   ├── user-service        ─┐
                                   ├── product-service      ├──► PostgreSQL
                                   ├── order-service ───────┤    (4 databases)
                                   │     ├─ validates user  │
                                   │     ├─ reserves stock  │
                                   │     └─ notifies        │
                                   └── notification-service ┘
```

Order flow is a real saga: the gateway forwards an idempotency key, `order-service` validates the customer, prices the basket from `product-service`, reserves stock item by item, and compensates every prior reservation if any later item fails.

## Technology stack

Docker · Docker Compose · Kubernetes 1.34 (Kind) · Helm 4 · Argo CD 2.13 · Prometheus · Grafana · Alertmanager · Loki · Promtail · Python 3.12 · FastAPI · SQLAlchemy 2 · PostgreSQL 16 · React 18 · TypeScript · Vite · GitHub Actions · Jenkins · Trivy · Checkov · Bandit · pip-audit

## Repository structure

```
applications/          six deployable services (5 FastAPI + frontend) with Dockerfiles and tests
  shared/service_kit/  logging, metrics, errors, DB and resilient HTTP client shared by services
platform-api/          read-only FastAPI backend for the operations dashboard
kubernetes/            core (ConfigMap/Postgres/platform-api/ingress), base, overlays, namespaces, policies
helm/                  reusable microservice chart + generated per-service charts
argocd/                AppProject, app-of-apps, 13 Applications, sync-wave ordering
monitoring/            Prometheus rules/scrape config, Alertmanager, Grafana provisioning + 6 dashboards
logging/               Loki + Promtail
.github/workflows/     ci.yml, security.yml, deploy.yml
jenkins/               Jenkinsfile (parallel tests, scans, approval gate)
security/              scan output, findings.json consumed by the dashboard
tests/                 manifest policy, Helm, repository hygiene and live integration suites
scripts/               local deploy, secrets, git remote, smoke test, CI helper
docs/                  architecture, install, operations, security, testing, interview pack
screenshots/           real captures from this environment
demo/                  recording script and checklist
```

## Prerequisites

Docker Desktop ≥ 4.30 (WSL2 backend, 4 GB RAM allocated), kubectl ≥ 1.29, Helm ≥ 3.14, Kind ≥ 0.23, Python 3.12, Node 20+, Git. Optional: Trivy, Checkov, kubeconform.

## Quick start — Docker Compose (fastest)

```powershell
docker compose --profile observability up -d --build
./scripts/smoke-test.ps1
```

| Endpoint | URL |
|---|---|
| Dashboard | http://localhost:13000/ops |
| Storefront demo | http://localhost:13000/store |
| Gateway API | http://localhost:18005/api/health |
| Platform API | http://localhost:18081/api/health |
| Grafana | http://localhost:13001 (admin/admin, local only) |
| Prometheus | http://localhost:19090 |

Compose runs `platform-api` with `PLATFORM_DEMO_MODE=true` because the bridge network cannot reach the Kind API server; the dashboard shows a permanent **DEMO DATA** banner in that mode. Live cluster data comes from the in-cluster deployment.

## Kubernetes deployment (Kind)

```powershell
kind create cluster --config kubernetes/kind-config.yaml
kubectl apply -f kubernetes/namespaces/namespaces.yaml
./scripts/create-dev-secrets.ps1
kubectl apply -k kubernetes/overlays/development
kubectl -n platform get pods
```

Ingress is exposed on **http://localhost:18080** (`/`, `/platform`, `/gateway`) because ports 8080/8443 were already occupied on the development machine — see `docs/TROUBLESHOOTING.md`.

Full instructions: [docs/INSTALLATION.md](docs/INSTALLATION.md) · [docs/KUBERNETES_SETUP.md](docs/KUBERNETES_SETUP.md)

## Helm

```bash
helm lint helm/microservice
helm lint helm/charts/api-gateway
helm template api-gateway helm/charts/api-gateway --namespace platform
helm upgrade --install api-gateway helm/charts/api-gateway -n platform
```

Charts are generated from the single hardened chart so each service installs standalone: `python tools/generate_helm_charts.py`. Details: [docs/HELM_DEPLOYMENT.md](docs/HELM_DEPLOYMENT.md).

## Argo CD GitOps

```powershell
kubectl apply -f argocd/projects.yaml
kubectl apply -f argocd/app-of-apps.yaml
kubectl -n argocd get applications
```

Sync waves: namespaces (-10) → core (-5) → services (0-1) → policies (2) → monitoring/logging (3) → production (10, manual). Development is `automated` with `selfHeal`; `platform-production` has no automated block and waits for a human. Details: [docs/ARGOCD_GITOPS.md](docs/ARGOCD_GITOPS.md).

## Monitoring

Prometheus scrapes every service's `/metrics`, kube-state-metrics, node-exporter and cAdvisor. Six dashboards are provisioned as code (`tools/generate_dashboards.py`). Alerts cover crash loops, CPU/memory pressure, deployment availability, 5xx ratio, p95 latency and volume exhaustion with runbook links. Details: [docs/MONITORING.md](docs/MONITORING.md).

## Testing

```bash
# Per service (module names collide if run in one process)
python -m pytest applications/user-service -q
python -m pytest applications/order-service -q
python -m pytest platform-api -q

# Cross-cutting
python -m pytest tests -q --ignore=tests/test_integration_live.py   # 47 static tests
python -m pytest tests/test_integration_live.py                     # needs a running stack
pytest applications/user-service -q                                  # 8 tests
```

Status in this environment: **46 backend tests pass**, **47 static/policy tests pass**, frontend `npm run build` and `npm run typecheck` pass. See [docs/TESTING.md](docs/TESTING.md) for the full matrix and what could not run.

## CI/CD

`.github/workflows/ci.yml` runs lint, a per-service test matrix, frontend typecheck/build, kustomize + kubeconform + Helm validation, and multi-arch image builds (pushing only on `main`). `security.yml` adds Trivy filesystem/config/image scans, Checkov, gitleaks and a forbidden-file guard. `deploy.yml` updates image tags in Git (never `kubectl apply`) and requires a GitHub Environment approval for production. `jenkins/Jenkinsfile` mirrors the same stages.

Both workflows run on GitHub and are green on main (CI run 44495990389, Security run 44495990307). Image publishing to GHCR is opt-in via the PUSH_IMAGES repository variable because this account cannot currently create packages; builds and scans run regardless.

## Security

Non-root pods, dropped capabilities, `RuntimeDefault` seccomp, read-only root filesystems, default-deny NetworkPolicies with explicit allow-lists, a read-only `ClusterRole` for the dashboard (no secrets, no write verbs), ResourceQuota/LimitRange, and out-of-band secret creation (never committed). Scans: `security/SECURITY_REPORT.md`, summary in [docs/SECURITY.md](docs/SECURITY.md).

## Screenshots

| View | File |
|---|---|
| Operations dashboard | `screenshots/01-dashboard-overview.png` |
| Pods | `screenshots/02-pods.png` |
| GitOps status | `screenshots/03-gitops-status.png` |
| Monitoring | `screenshots/04-monitoring.png` |
| Security findings | `screenshots/05-security.png` |
| Grafana | `screenshots/06-grafana-dashboard.png` |
| Prometheus targets | `screenshots/07-prometheus-targets.png` |
| Kubernetes workloads | `screenshots/08-kubectl-workloads.png` |
| Argo CD applications | `screenshots/09-argocd-applications.png` |
| Security scan output | `screenshots/10-security-scan.png` |

## Troubleshooting

[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) covers Docker, cluster connectivity, ImagePullBackOff, CrashLoopBackOff, Pending pods, service DNS, ingress, Helm, Argo CD sync, Prometheus scraping, Grafana and Loki.

## Known limitations

- Local Kind runs a single node (3 GB), so the production overlay is validated and rendered but not fully scheduled; the manual-sync gate is demonstrated by its `OutOfSync` state.
- Kubernetes manifests include `Secret` **examples** only. Real values are generated by `scripts/create-dev-secrets.ps1` and never committed.
- The repository ships a local Git remote workflow (`scripts/start-local-git-remote.ps1`) for offline GitOps; point Application `repoURL`s at GitHub for a hosted setup.
- Multi-node scheduling, TLS certificates and external identity providers are out of scope for a laptop-scale demo.

## Future enhancements

Progressive delivery with Argo Rollouts, External Secrets Operator, multi-arch image promotion with signing (cosign/SLSA), Thanos for long-term metrics, OpenTelemetry tracing, and KEDA for queue-driven scaling.

## License

MIT — see [LICENSE](LICENSE).
