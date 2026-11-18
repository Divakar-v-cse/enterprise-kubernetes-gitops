# Deployment guide

Three supported paths. Pick one; do not mix Helm and kustomize for the same objects in the same namespace.

## Path A — Docker Compose (local demo)

```powershell
docker compose --profile observability up -d --build
./scripts/smoke-test.ps1
```

Ten containers, no cluster. Dashboard at http://localhost:13000/ops (demo mode, clearly labelled). Use this for UI review and API walkthroughs.

## Path B — kubectl + kustomize (fast cluster path)

```powershell
kind create cluster --config kubernetes/kind-config.yaml

kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.0/deploy/static/provider/kind/deploy.yaml
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system patch deployment metrics-server --type=json `
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

docker compose build
foreach ($img in @('api-gateway','user-service','product-service','order-service',
                   'notification-service','frontend','platform-api')) {
  kind load docker-image "platform/$img:1.0.0" --name gitops-platform
}

kubectl apply -f kubernetes/namespaces/namespaces.yaml
./scripts/create-dev-secrets.ps1
kubectl apply -k kubernetes/overlays/development
kubectl -n platform rollout status deployment/api-gateway --timeout=180s
```

Or one command: `./scripts/deploy-local.ps1` (add `-SkipMonitoring` for a smaller footprint).

Verify:

```powershell
curl http://localhost:18080/platform/api/health
curl http://localhost:18080/gateway/api/health
```

## Path C — Argo CD (GitOps, recommended)

```powershell
# 1. Argo CD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v2.13.2/manifests/install.yaml
kubectl -n argocd rollout status deployment/argocd-server --timeout=300s

# 2. A Git remote Argo CD can clone
#    offline demo:
./scripts/start-local-git-remote.ps1      # git daemon on 9418
#    or GitHub: replace repoURL in argocd/**/*.yaml with your HTTPS URL

# 3. Root application
kubectl apply -f argocd/projects.yaml
kubectl apply -f argocd/app-of-apps.yaml
kubectl -n argocd get applications -w
```

Ordering is enforced by sync waves: namespaces → core → services → policies → monitoring/logging → production (manual).

Promote a change:

```powershell
# edit code, commit, push to the remote Argo CD watches
git push
kubectl -n argocd annotate application api-gateway argocd.argoproj.io/refresh=normal --overwrite
```

Production requires a human:

```powershell
argocd app diff platform-production
argocd app sync platform-production
```

## Post-deployment verification

```powershell
kubectl -n platform get deploy,pods,hpa,pdb
kubectl -n platform get networkpolicy
kubectl -n monitoring get pods
kubectl -n argocd get applications
curl http://localhost:18080/gateway/api/health
kubectl -n platform logs deploy/order-service --tail=20
```

Expected: every Deployment `READY n/n`, HPAs reporting CPU targets, Argo applications `Synced/Healthy` except `platform-production` (`OutOfSync` by design).

## Rollout and rollback

| Action | GitOps (preferred) | kubectl (diagnosis only) |
|---|---|---|
| Deploy | Commit image tag change, push | `kubectl set image ...` (self-heal reverts it) |
| Pause | Edit the Application's sync policy | — |
| Rollback | `git revert` + push | `kubectl rollout undo deployment/<name>` |
| Verify | `argocd app wait <app> --health` | `kubectl rollout status` |

## Environment differences

| Setting | Development | Production |
|---|---|---|
| Namespace | `platform` | `platform-prod` |
| Replicas | 1 | 3 (2 for notification) |
| Argo sync | automated + selfHeal | manual |
| Log level | DEBUG | INFO |
| Ingress | HTTP on 18080 | TLS redirect enabled |
| Secrets | `scripts/create-dev-secrets.ps1` | External Secrets / Sealed Secrets |

## Teardown

```powershell
kubectl delete -k kubernetes/overlays/development
kind delete cluster --name gitops-platform
docker compose --profile observability down -v
```

## Resource expectations

| Path | Docker memory | Cluster memory used |
|---|---|---|
| Compose (app only) | 1.2 GB | — |
| Compose + observability | 2.0 GB | — |
| Kind + apps | — | ~900 MB |
| Kind + apps + monitoring + logging + Argo CD | — | ~2.4 GB |

Allocate at least 4 GB to Docker Desktop (8 GB host recommended). On a smaller machine, skip the observability profile and apply only `kubernetes/overlays/development`.
