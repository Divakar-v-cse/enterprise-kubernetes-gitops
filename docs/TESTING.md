# Testing

## Results in this environment

| Suite | Command | Result |
|---|---|---|
| api-gateway | `pytest applications/api-gateway -q` | **8 passed** |
| user-service | `pytest applications/user-service -q` | **8 passed** |
| product-service | `pytest applications/product-service -q` | **6 passed** |
| order-service | `pytest applications/order-service -q` | **7 passed** |
| notification-service | `pytest applications/notification-service -q` | **5 passed** |
| platform-api | `pytest platform-api -q` | **12 passed** |
| Manifest/Helm/hygiene | `pytest tests -q --ignore=tests/test_integration_live.py` | **47 passed** |
| Frontend typecheck | `npm run typecheck` | passed |
| Frontend build | `npm run build` | passed (dist emitted) |
| Docker builds | `docker compose build` | 7/7 images built |
| Helm lint | `helm lint helm/microservice helm/charts/*` | passed |
| Helm render | `helm template …` (all charts) | passed |

Total: **93 automated Python tests**, all passing.

Run one suite at a time: every service uses the package name `app`, so a single pytest process would import the wrong module.

## Test layers

### 1. Service unit/API tests (`applications/*/tests/`)

Each suite sets `DATABASE_URL=sqlite+aiosqlite:///…` before importing the app, so no PostgreSQL is needed. Coverage:

- health endpoints and `/metrics` output
- internal-token authorization (401 path)
- validation envelopes (422) and pagination bounds
- duplicate email/SKU conflicts (409)
- atomic stock reservation, insufficient stock leaves state unchanged
- order saga: pricing, compensation on partial failure, unknown user/product,
  notification failure → `notification_pending`, idempotency replay

Order tests replace the three upstreams with stateful fakes (`FakeClient`) so failure paths are deterministic.

### 2. Platform API tests (`platform-api/tests/`)

Demo mode with auth enabled: bearer required, pagination meta, filtering, source labelling (`meta.source="demo"`), GitOps meta counts, security finding shape, log level filtering, Prometheus exposition.

### 3. Static policy tests (`tests/test_manifests.py`)

Parses every manifest under `kubernetes/`, `monitoring/`, `logging/` and asserts:

- every Deployment: requests+limits, liveness+readiness probes, non-root pod, seccomp `RuntimeDefault`, no privilege escalation, dropped `ALL` capabilities, pinned image tag
- services are `ClusterIP` by default
- `default-deny-all` NetworkPolicy exists with both directions
- PDBs cover all six stateless services
- HPA targets CPU for gateway and order
- namespaces declare Pod Security labels
- ResourceQuota and LimitRange exist
- platform-api ClusterRole grants only `get`/`list` and never touches secrets
- no literal secret values (only `REPLACE_ME` placeholders)
- ingress backends are limited to frontend/gateway/platform-api
- every Dockerfile switches to a non-root USER and declares HEALTHCHECK

### 4. Helm tests (`tests/test_helm_charts.py`)

All six charts exist, lint, render Deployment+Service+PDB, keep three probes, resources, read-only root FS, and correct scrape annotations. Gateway and order must render an HPA with a CPU target ≤ 70 %.

### 5. Repository hygiene (`tests/test_repository_hygiene.py`)

No `.env`, `kubeconfig`, private keys or credential patterns anywhere; `.gitignore` covers runtime artifacts; the example secret contains only placeholders.

### 6. Live integration (`tests/test_integration_live.py`)

Skipped automatically unless a gateway answers. Against a running stack it verifies dependency health, order lifecycle (stock 10 → 7), notification delivery, idempotent replay, 409 on insufficient stock with untouched inventory, 401 without an API key, metrics exposition and pagination.

```powershell
docker compose --profile observability up -d
python -m pytest tests/test_integration_live.py -q
```

### 7. Container and manifest validation

```bash
docker compose config --quiet
kubectl kustomize kubernetes/overlays/development | kubeconform -strict -summary -
helm template api-gateway helm/charts/api-gateway | kubeconform -strict -summary -
```

## What could not be executed here

| Item | Reason | How to run |
|---|---|---|
| GitHub Actions execution | **Executed on GitHub** after the CI fixes: CI and Security both pass on main (runs 44495990389 / 44495990307) | gh run list --branch main |
| Frontend component tests | No test runner or DOM harness installed; logic verified through typecheck + build | `npm i -D vitest @testing-library/react` then `npm test` |
| HPA scale-out under load | Single-node Kind with a 3 GB budget | `k6 run` or `hey -z 3m` against the gateway, then `kubectl get hpa -w` |
| Kubescape | Not installed in this environment | `curl -s https://raw.githubusercontent.com/kubescape/kubescape/master/install.sh \| /bin/bash` then `kubescape scan framework nsa` |
| Multi-node scheduling / PDB drain demo | One node | Create a 2-node Kind cluster and `kubectl drain` |

## CI

`.github/workflows/ci.yml` runs the six suites as a matrix with coverage, frontend typecheck/build, kustomize + kubeconform, Helm lint/template, and image builds. `.github/workflows/security.yml` adds Trivy, Checkov, gitleaks and a tracked-secret guard.
