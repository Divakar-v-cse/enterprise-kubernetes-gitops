# Installation

Local install of the Enterprise Kubernetes GitOps Platform: Kind cluster, images,
manifests, Argo CD, observability. Each stage ends with a **Verify** line — don't
continue until it passes. `scripts/` is PowerShell 7; bash equivalents are inline.

## 1. Prerequisites

| Tool | Version | Why it is needed |
| --- | --- | --- |
| Docker Desktop (WSL2 backend) | current | Builds images, hosts the Kind node, runs Compose |
| kubectl | 1.36 | Apply kustomize, wait for rollouts, port-forward |
| Helm | 4.1 (charts also lint with Helm 3) | Lint/render `helm/microservice` + `helm/charts/*` |
| kind | 0.30.0 | Creates cluster `gitops-platform` (Kubernetes v1.34.0) |
| Python | 3.12 | Service test suites; static file server for the Git remote |
| Node.js | 20 or 22 | Frontend `npm run build` |
| git | recent | Clone, local Git remote for Argo CD, drift/rollback demos |
| trivy, checkov, kubeconform | optional | Scans and manifest schema validation |

```powershell
docker version; kubectl version --client; helm version; kind --version; python --version; node --version
```

## 2. Docker Desktop setup

Settings → General → **Use the WSL 2 based engine**; Resources → Memory **≥ 4 GB**
(8 GB host recommended, §16). Minikube's docker driver is unsupported on Windows —
that is why this repo uses Kind.

```powershell
docker info --format '{{.OSType}} {{.MemTotal}} {{.NCPU}}'; docker compose version; docker run --rm hello-world
```

```bash
sudo usermod -aG docker "$USER"   # log out and back in once
docker info --format '{{.MemTotal}}'; docker compose version
```

**Verify:** `docker ps` works and `docker info` reports ≥ 4 GiB of memory.

## 3. Kind cluster creation

```powershell
kind create cluster --name gitops-platform --image kindest/node:v1.34.0 `
  --config kubernetes/kind-config.yaml --wait 240s
```

```bash
kind create cluster --name gitops-platform --image kindest/node:v1.34.0 --config kubernetes/kind-config.yaml --wait 240s
```

`kind-config.yaml` maps node 80→**18080** and 443→**18443**. Keep those ports: 8080/8443
are already taken on this machine, and reverting makes `kind create` fail with
`Bind for 0.0.0.0:8443 failed: port is already allocated`.

```powershell
kind get clusters
kubectl get nodes -o wide
kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.kubeletVersion}'
```

**Verify:** `gitops-platform` listed, node `Ready`, kubelet `v1.34.0`.

Ingress controller and metrics-server (needed for §10 and HPA):

```powershell
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.0/deploy/static/provider/kind/deploy.yaml
kubectl -n ingress-nginx wait --for=condition=Available deployment/ingress-nginx-controller --timeout=240s
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system patch deployment metrics-server --type=json `
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
kubectl -n kube-system rollout status deployment/metrics-server --timeout=180s
```

**Verify:** `kubectl -n ingress-nginx get pods` is `Running`; `kubectl top nodes` returns
numbers instead of `error: Metrics API not available`.

## 4. kubectl context

```powershell
kubectl config get-contexts
kubectl config use-context kind-gitops-platform
```

```bash
kubectl config use-context kind-gitops-platform
```

**Verify:** `kubectl cluster-info` prints the control plane URL; `kubectl -n kube-system
get pods` shows `coredns`, `kube-proxy`, `metrics-server` running.

## 5. Helm

```powershell
helm version
helm lint helm/microservice
Get-ChildItem helm/charts -Directory | ForEach-Object { helm lint $_.FullName }
helm template api-gateway helm/charts/api-gateway --namespace platform | Out-Null
```

```bash
helm version; helm lint helm/microservice
for chart in helm/charts/*/; do helm lint "$chart"; done
helm template api-gateway helm/charts/api-gateway --namespace platform > /dev/null
```

**Verify:** every chart prints `1 chart(s) linted, 0 chart(s) failed`.

## 6. Build and load images

```powershell
docker compose --profile observability build
foreach ($img in @("platform/api-gateway:1.0.0","platform/user-service:1.0.0","platform/product-service:1.0.0",
    "platform/order-service:1.0.0","platform/notification-service:1.0.0","platform/frontend:1.0.0","platform/platform-api:1.0.0")) {
  kind load docker-image $img --name gitops-platform
}
```

```bash
docker compose --profile observability build
for img in platform/api-gateway:1.0.0 platform/user-service:1.0.0 platform/product-service:1.0.0 \
           platform/order-service:1.0.0 platform/notification-service:1.0.0 \
           platform/frontend:1.0.0 platform/platform-api:1.0.0; do
  kind load docker-image "$img" --name gitops-platform
done
```

`applications/frontend/package.json` pins `overrides.rollup=4.24.0`. Keep it: rollup
4.68.6 fails on `react-dom/client.js` with `Code is nested too deeply`, aborting the
frontend image build.

**Verify:** `docker exec -it gitops-platform-control-plane crictl images` lists all seven
`platform/*` tags.

## 7. Secrets

```powershell
kubectl apply -f kubernetes/namespaces/namespaces.yaml
./scripts/create-dev-secrets.ps1 -Namespace platform
```

No PowerShell script on Linux — create the same four keys directly:

```bash
kubectl apply -f kubernetes/namespaces/namespaces.yaml
kubectl -n platform create secret generic platform-secrets \
  --from-literal=POSTGRES_PASSWORD="$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 32)" \
  --from-literal=INTERNAL_API_TOKEN="$(openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c 48)" \
  --from-literal=PUBLIC_API_KEY="$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 32)" \
  --from-literal=PLATFORM_API_TOKEN="$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 32)"
```

**Verify:** `kubectl -n platform get secret platform-secrets -o jsonpath='{.data}'` shows
the four keys. Values are random per install and never committed; `-Force` rotates them,
after which `kubectl -n platform rollout restart deploy` is required.

## 8. Deploy with kubectl/kustomize (fast path)

```powershell
kubectl apply -k kubernetes/overlays/development
kubectl -n platform rollout status deployment/postgres --timeout=180s
foreach ($d in @("user-service","product-service","order-service","notification-service","api-gateway","platform-api","frontend")) {
  kubectl -n platform rollout status "deployment/$d" --timeout=240s
}
```

```bash
kubectl apply -k kubernetes/overlays/development
kubectl -n platform rollout status deployment/postgres --timeout=180s
for d in user-service product-service order-service notification-service api-gateway platform-api frontend; do
  kubectl -n platform rollout status "deployment/$d" --timeout=240s
done
```

One-shot equivalent, also installing ingress, metrics-server, images, monitoring, logging:

```powershell
./scripts/deploy-local.ps1                            # full run
./scripts/deploy-local.ps1 -SkipCluster -SkipImages   # manifests only
```

**Verify:** `kubectl -n platform get pods` all `Running`; `curl.exe -s -o NUL -w
"%{http_code}`n" http://localhost:18080/platform/api/health` returns `200`.

## 9. Deploy with Argo CD (GitOps path)

```powershell
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v2.13.2/manifests/install.yaml
kubectl -n argocd rollout status deployment/argocd-server --timeout=300s
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" |
  ForEach-Object { [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($_)) }
kubectl -n argocd port-forward svc/argocd-server 8080:443     # https://localhost:8080, admin
```

Expect a brief window where `argocd-redis` and pods depending on it are not ready until
the install manifests create the `argocd-redis` secret — re-check, don't reinstall.

```powershell
./scripts/start-local-git-remote.ps1     # serves :8099, pushes HEAD -> main
kubectl apply -f argocd/projects.yaml
kubectl apply -f argocd/app-of-apps.yaml
kubectl -n argocd get applications -w
```

Argo CD pulls `http://host.docker.internal:8099/enterprise-kubernetes-gitops.git`; re-run
the script after each commit or Argo keeps comparing the old revision.

**Verify:** `platform-app-of-apps` and children (`platform-core`, `api-gateway`, …,
`platform-monitoring`, `platform-logging`) are `Synced`/`Healthy`. `platform-production`
stays `OutOfSync` until a human syncs it.

## 10. Ingress and URLs

| Path | Backend (port) | Kind URL |
| --- | --- | --- |
| `/` | `frontend` (80) | `http://localhost:18080/` |
| `/platform` | `platform-api` (8080) | `http://localhost:18080/platform/api/health` |
| `/gateway` | `api-gateway` (8000) | `http://localhost:18080/gateway/api/health` |

The Ingress rewrites `/platform/*` and `/gateway/*` to `/*` (`rewrite-target: /$2`).

**Verify:** `curl.exe -s http://localhost:18080/gateway/api/health` returns JSON;
`curl.exe -s -o NUL -w "%{http_code}`n" http://localhost:18080/` returns `200`.

## 11. Prometheus, Grafana, Alertmanager

```powershell
kubectl apply -k monitoring
kubectl -n monitoring rollout status deployment/prometheus --timeout=180s
kubectl -n monitoring port-forward svc/prometheus-server 9090:9090   # http://localhost:9090
kubectl -n monitoring port-forward svc/grafana 3000:3000             # http://localhost:3000
kubectl -n monitoring port-forward svc/alertmanager 9093:9093        # http://localhost:9093
```

```bash
kubectl apply -k monitoring
kubectl -n monitoring port-forward svc/grafana 3000:3000
```

**Verify:** `kubectl -n monitoring get pods` all `Running`; Prometheus → *Status →
Targets* shows `prometheus`, `node-exporter`, `kube-state-metrics`, `kubelet-cadvisor`
and `platform-pods` as `UP`. An empty `platform-pods` job means no pod carries the
`prometheus.io/scrape` annotation.

## 12. Loki and Promtail

```powershell
kubectl apply -k logging
kubectl -n logging rollout status daemonset/promtail --timeout=180s
kubectl -n logging port-forward svc/loki 3100:3100
```

**Verify:** `curl.exe -s http://localhost:3100/loki/api/v1/labels` returns label names;
`kubectl -n logging logs daemonset/promtail --tail=20` shows one target per container
(`connection refused` there means Loki was not ready — restart the DaemonSet).

## 13. Platform dashboard and storefront

In-cluster (live data): open `http://localhost:18080/ops`, then `/ops/settings` and set
Platform API `http://localhost:18080/platform`, gateway `http://localhost:18080/gateway`,
plus the bearer token / API key printed by `create-dev-secrets.ps1`.

```powershell
cd applications/frontend; npm install; npm run dev    # http://localhost:5173
docker compose up -d --build                          # UI http://localhost:13000/ops
```

Compose runs `platform-api` with `PLATFORM_DEMO_MODE=true` (the bridge network cannot
reach the Kind API server), so ops pages show the DEMO DATA banner; live data comes from
the in-cluster deployment.

**Verify:** `curl.exe -s http://localhost:18081/api/health` (Compose) and
`curl.exe -s http://localhost:18080/platform/api/health` (Kind) return `"status":"ok"`;
`/store` lists catalog items from `api-gateway`.

| Component | Kind | Compose |
| --- | --- | --- |
| Frontend | 18080 | 13000 |
| Platform API | 18080 `/platform` | 18081 |
| API gateway | 18080 `/gateway` | 18005 |
| user / product / order / notification | in-cluster only | 18001 / 18002 / 18003 / 18004 |
| PostgreSQL | in-cluster only | 15432 |
| Prometheus / Grafana / Alertmanager | 9090 / 3000 / 9093 (port-forward) | 19090 / 13001 / 19093 |

## 14. Run all tests

Python suites run **per service** — together they collide on the `app` module name.

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements-dev.txt
foreach ($svc in @("api-gateway","user-service","product-service","order-service","notification-service")) {
  python -m pytest "applications/$svc" -q
}
python -m pytest platform-api -q
python -m pytest tests -q          # cross-cutting: manifests, helm, hygiene, live
ruff check applications platform-api tools tests
```

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
for svc in api-gateway user-service product-service order-service notification-service; do
  python -m pytest "applications/$svc" -q || exit 1
done
python -m pytest platform-api -q; python -m pytest tests -q
ruff check applications platform-api tools tests
```

```powershell
cd applications/frontend; npm ci; npm run typecheck; npm run build; cd ../..
Get-ChildItem helm/charts -Directory | ForEach-Object { helm template $_.Name $_.FullName --namespace platform | Out-Null }
docker compose config --quiet
```

**Verify:** all green. `tests/test_integration_live.py` needs a reachable cluster; it is
the only suite that reads the live API.

## 15. Teardown

```powershell
kind delete cluster --name gitops-platform
docker compose --profile observability down -v
Remove-Item -Recurse -Force ..\.gitops-remote -ErrorAction SilentlyContinue
```

```bash
kind delete cluster --name gitops-platform
docker compose --profile observability down -v
rm -rf ../.gitops-remote
```

Stop `start-local-git-remote.ps1` with `Ctrl+C` first.

**Verify:** `kind get clusters` no longer lists `gitops-platform`; `docker ps` shows no
`platform/*` containers.

## 16. Resource requirements

| Resource | Minimum | Notes |
| --- | --- | --- |
| Docker Desktop memory | 4 GB | 8 GB host RAM recommended |
| Kind node | 3 GB / 4 CPU | Single control-plane node |
| Full stack | ≈2.5 GB cluster memory | apps + monitoring + logging + Argo CD |
| Disk | ≈10 GB free | Images, node, Prometheus/Grafana volumes |

Keep the development overlay at 1 replica per service (it patches HPA to
`minReplicas: 1 / maxReplicas: 3`). The production overlay does not fit a laptop node.

## 17. Minikube alternative

Minikube's **docker driver is unsupported on Windows**, so use Kind on Windows. On Linux:

```bash
minikube start --driver=docker --cpus=4 --memory=4096 --kubernetes-version=v1.34.0
minikube addons enable ingress; minikube addons enable metrics-server
eval "$(minikube docker-env)"      # build straight into the node, no `kind load`
docker compose --profile observability build
```

Then follow §7–§14 with two differences: no `kind load docker-image` (images built under
`minikube docker-env` are already present), and Ingress is reached via `minikube tunnel`
instead of host ports 18080/18443.

**Verify:** `kubectl get nodes` is `Ready`, `kubectl top nodes` works, and
`kubectl -n platform get ingress` shows an ADDRESS once the tunnel is up.
