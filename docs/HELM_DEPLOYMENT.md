# Helm deployment

## Chart layout

```
helm/
├── microservice/          # the hardened source-of-truth chart
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/         # deployment, service, hpa, pdb, serviceaccount, _helpers, NOTES
└── charts/                # generated, self-contained per-service charts
    ├── api-gateway/
    ├── user-service/
    ├── product-service/
    ├── order-service/
    ├── notification-service/
    └── frontend/
```

One chart keeps six releases consistent; the generator (`tools/generate_helm_charts.py`) writes a chart per service so each can be installed, linted and referenced by Argo CD independently, without `helm dependency build`.

```powershell
python tools/generate_helm_charts.py
```

## What the chart gives you

| Feature | Implementation |
|---|---|
| Three probes | startup `/health/live`, readiness `/health/ready`, liveness `/health/live` (frontend uses `/healthz`) |
| Hardened security | `runAsNonRoot` UID 10001, seccomp `RuntimeDefault`, dropped caps, read-only root FS, `/tmp` emptyDir |
| Resources | Per-service requests/limits in `values.yaml` |
| Disruption control | PDB `minAvailable: 1`, `maxSurge: 1` / `maxUnavailable: 0` |
| Autoscaling | Optional HPA, CPU target configurable |
| Metrics | Pod annotations `prometheus.io/scrape` + `prometheus.io/port` |
| Configuration | `configMapRef: platform-config`, `env`, `secretEnv` (secret-first ordering so `$(VAR)` expansion works) |

## Validate

```bash
helm lint helm/microservice
for chart in helm/charts/*/; do helm lint "$chart"; done

helm template api-gateway helm/charts/api-gateway --namespace platform | head -40
helm template api-gateway helm/charts/api-gateway --namespace platform --set replicaCount=3 --debug
```

Automated equivalent: `python -m pytest tests/test_helm_charts.py -q` (lints, renders, asserts probes/resources/security and HPA presence).

## Install

```bash
kubectl apply -f kubernetes/namespaces/namespaces.yaml
kubectl apply -k kubernetes/core            # ConfigMap, PostgreSQL, platform-api, ingress
./scripts/create-dev-secrets.ps1            # or kubectl create secret

helm upgrade --install api-gateway helm/charts/api-gateway \
  --namespace platform --create-namespace \
  --set replicaCount=2 --wait --timeout 5m
```

Repeat per service. `helm list -n platform` should show six releases.

## Override values per environment

Development (single replica, dev log level):

```bash
helm upgrade --install order-service helm/charts/order-service -n platform \
  --set replicaCount=1 \
  --set image.tag=1.0.0 \
  --set env[0].value=development
```

Production shape (three replicas, higher limits, autoscaling):

```bash
helm upgrade --install order-service helm/charts/order-service -n platform-prod \
  --set replicaCount=3 \
  --set autoscaling.enabled=true \
  --set autoscaling.minReplicas=3 --set autoscaling.maxReplicas=8 \
  --set resources.limits.cpu=1 --set resources.limits.memory=512Mi
```

Argo CD applies the same overrides inline (`spec.source.helm.values`), so Git stays the single source of truth.

## Upgrades and rollback

```bash
helm history api-gateway -n platform
helm rollback api-gateway 1 -n platform
helm upgrade --install api-gateway helm/charts/api-gateway -n platform --atomic --timeout 5m
```

`--atomic` rolls back automatically if the release does not become ready. In the GitOps path, prefer reverting the Git commit — Argo CD then reconciles the cluster.

## Common values

| Key | Default | Meaning |
|---|---|---|
| `replicaCount` | 2 (generated: 1) | Replicas when HPA is disabled |
| `image.repository` / `image.tag` | `platform/<service>` / `1.0.0` | Immutable tag recommended |
| `configMapRef` | `platform-config` | Shared ConfigMap |
| `secretEnv` | per service | `[{name, secretName, key}]` |
| `autoscaling.enabled` | false (true for gateway/order/product) | Enables HPA |
| `pdb.minAvailable` | 1 | Disruption budget |
| `probes.*.path` | health endpoints | Override for the frontend |
| `extraVolumes` / `extraVolumeMounts` | `[]` | Writable cache for NGINX |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Error: cannot re-use a name that is still in use` | Release exists unmanaged | `helm uninstall` then reinstall, or `helm upgrade --install` |
| Pods `CreateContainerConfigError` | Missing `platform-secrets` or `platform-config` | Create the secret / apply `kubernetes/core` |
| `UPGRADE FAILED: context deadline exceeded` | Readiness never passed | `kubectl -n platform describe pod` and check probes |
| HPA shows `<unknown>` | No CPU request or metrics-server down | Set requests, verify `kubectl top pods` |
