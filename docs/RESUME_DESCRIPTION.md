# Resume description

## One-line summary

Built a production-shaped Kubernetes GitOps platform delivering a six-service microservices application with automated Argo CD deployment, Prometheus/Grafana observability, autoscaling and default-deny network security — fully reproducible on a laptop.

## Bullet points (pick 4-6)

- Designed and implemented **five FastAPI microservices plus a React/TypeScript operations dashboard**, backed by PostgreSQL with a database per bounded context and 93 automated tests across unit, API, manifest-policy and Helm layers.
- Implemented a **distributed order workflow** with saga-style stock reservation, compensating transactions on partial failure, idempotency keys and circuit-broken service-to-service calls (timeouts, retries, per-target breaker).
- Containerised all services with **multi-stage builds running as non-root (UID 10001)** with read-only root filesystems, dropped capabilities, seccomp profiles and container health checks; 7 images build reproducibly via Docker Compose.
- Authored **Kubernetes manifests for 7 workloads** with startup/readiness/liveness probes, resource requests and limits, PodDisruptionBudgets, HPAs, ResourceQuota/LimitRange, and **default-deny NetworkPolicies** with explicit service-to-service allow-lists.
- Built a **reusable Helm chart** rendered into six self-contained per-service charts, validated with `helm lint` and `helm template` locally and in CI.
- Implemented **GitOps with Argo CD** using an app-of-apps pattern with sync waves, automated sync + self-healing for development, and a **manual approval gate for production**; every rollback is a Git revert.
- Instrumented the platform with **Prometheus metrics, 6 provisioned Grafana dashboards and 11 alert rules** (crash loops, 5xx ratio, p95 latency, CPU/memory saturation, deployment availability, PVC pressure) with runbook links, plus **Loki/Promtail log aggregation** keyed by request ID.
- Built a **read-only platform API** enforcing least privilege (a `ClusterRole` limited to `get`/`list`, no secrets, no writes) that powers a 14-page dashboard and degrades to explicitly labelled demo data when the cluster is unreachable.
- Created **CI/CD pipelines in GitHub Actions and Jenkins** covering per-service test matrices, frontend build, image builds, Trivy/Checkov/Bandit/pip-audit scans, gitleaks secret scanning, kustomize + kubeconform + Helm validation, and Git-based deployment promotion with an environment approval gate.

## Skills demonstrated

Kubernetes · Docker · Helm · Argo CD · GitOps · Prometheus · Grafana · Alertmanager · Loki · FastAPI · SQLAlchemy · PostgreSQL · React · TypeScript · GitHub Actions · Jenkins · Trivy · Checkov · Bandit · RBAC · NetworkPolicy · HPA · PDB · Pod Security Standards · Bash/PowerShell · Python

## Interview talking point

> "The interesting part wasn't writing YAML — it was making the failure paths real. The order service reserves stock item by item and compensates when a later item fails; the dashboard is read-only by RBAC and labels demo data explicitly, so it can never lie about cluster state; and production is gated by the absence of an automated sync policy, not by a script someone can bypass."

## Scope note (be honest in interviews)

The cluster is a single-node Kind cluster sized for a laptop. The production overlay is rendered and validated but not fully scheduled there; multi-node scheduling, TLS automation and external identity are explicitly out of scope. State that up front — it reads as engineering judgement, not a gap.
