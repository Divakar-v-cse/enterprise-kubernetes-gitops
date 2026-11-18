# Argo CD — GitOps control plane

## Install (local Kind)

```powershell
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v2.13.2/manifests/install.yaml
kubectl -n argocd rollout status deployment/argocd-server --timeout=300s

# Initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" |
  ForEach-Object { [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($_)) }

kubectl -n argocd port-forward svc/argocd-server 8080:443
# https://localhost:8080  (admin / password above)
```

`argocd` CLI is optional; every step below also works through the UI.

## Register the Git repository

The committed Applications reference a **local Git server** so the demo works
without a GitHub account:

```powershell
./scripts/start-local-git-remote.ps1   # serves a bare clone on :8099
```

For a real remote, replace `repoURL` in `argocd/applications/*.yaml` and
`argocd/app-of-apps.yaml` with your repository URL, then commit. Never commit
credentials — use `argocd repo add` or a repository Secret.

Argo CD validates TLS for HTTPS remotes. The local server is plain HTTP, which
Argo CD accepts for unauthenticated repositories. If your Argo CD version
rejects it, register the repo with `--insecure`:

```powershell
argocd repo add http://host.docker.internal:8099/enterprise-kubernetes-gitops.git --insecure
```

## Deploy

```powershell
kubectl apply -f argocd/projects.yaml
kubectl apply -f argocd/app-of-apps.yaml
kubectl -n argocd get applications -w
```

Sync waves order the rollout:

| Wave | Application | Purpose |
|------|-------------|---------|
| -10 | platform-namespaces | Namespaces with Pod Security labels |
| -5 | platform-core | ConfigMap, PostgreSQL, platform API, ingress |
| 0 | api-gateway, user-service, product-service, notification-service, frontend | Helm releases |
| 1 | order-service | Depends on user/product/notification |
| 2 | platform-policies | NetworkPolicies, PDBs, quota, RBAC |
| 3 | monitoring, logging | Prometheus, Grafana, Alertmanager, Loki, Promtail |
| 10 | platform-production | Manual sync only (production gate) |

## Demonstrating the GitOps loop

```powershell
# 1. Change desired state in Git
(Get-Content helm/charts/order-service/values.yaml) -replace 'tag: "1.0.0"', 'tag: "1.0.0"' |
  Set-Content helm/charts/order-service/values.yaml

# 2. Commit and push to the local remote
git add . ; git commit -m "chore: bump order-service replica count"
git push local main

# 3. Argo CD detects the new revision (poll interval ~3 min, or click Refresh)
kubectl -n argocd get application order-service -o jsonpath='{.status.sync.revision}'

# 4. Force an immediate comparison
kubectl -n argocd annotate application order-service argocd.argoproj.io/refresh=normal --overwrite
```

## Drift detection

Argo CD compares live cluster state with Git every 3 minutes. To prove it:

```powershell
kubectl -n platform scale deployment/api-gateway --replicas=3
kubectl -n argocd get application api-gateway   # becomes OutOfSync
# With selfHeal enabled, Argo CD reverts it automatically.
```

## Rollback through Git

```powershell
git log --oneline -- helm/charts/api-gateway/values.yaml
git revert <bad-commit>
git push local main
# Argo CD syncs the reverted commit; the cluster returns to the previous state.
```

Application rollback inside Argo CD (`History and Rollback`) is also available
for emergency use, but Git remains the source of truth.

## Production approval

`platform-production` has **no** `automated` block. It shows `OutOfSync` until a
human with sync rights approves. That is the intended approval gate:

```powershell
argocd app diff platform-production
argocd app sync platform-production
```

## Notes and limitations

- The bundled repo is read-only for Argo CD; pushes come from your workstation.
- `platform-production` requires a `platform-secrets` Secret in `platform-prod`
  before a sync can succeed; create it the same way as the development one.
- Argo CD's own manifests are installed out-of-band (not self-managed) so a bad
  Application cannot lock you out of the control plane.
