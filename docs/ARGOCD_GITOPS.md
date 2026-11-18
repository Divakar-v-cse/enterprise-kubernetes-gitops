# Argo CD and GitOps

## Model

Git holds desired state; Argo CD reconciles the cluster toward it. Nothing in CI runs `kubectl apply` against the cluster — the deploy workflow only changes image tags in Git.

```
code change → CI (test/build/scan) → image tag committed → Argo CD compares
   → dev auto-sync (prune + selfHeal) → health verified
   → prod remains OutOfSync → human syncs
```

## Install

```powershell
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v2.13.2/manifests/install.yaml
kubectl -n argocd rollout status deployment/argocd-server --timeout=300s
kubectl -n argocd port-forward svc/argocd-server 8080:443
```

Initial admin password:

```powershell
$b64 = kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}'
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64))
```

## Repository configuration

Applications reference `git://host.docker.internal:9418/enterprise-kubernetes-gitops.git` for the offline demo, served by `scripts/start-local-git-remote.ps1` (`git daemon` + a bare repo). For GitHub, replace every `repoURL`:

```bash
grep -rl "host.docker.internal:9418" argocd/ | xargs sed -i 's#git://host.docker.internal:9418/enterprise-kubernetes-gitops.git#https://github.com/Divakar-v-cse/enterprise-kubernetes-gitops.git#'
```

Private repositories need credentials: `argocd repo add <url> --username ... --password ...` or a repository Secret. Never commit tokens.

> Plain HTTP (dumb protocol) does **not** work with Argo CD's go-git client — that is why the demo uses `git://`.

## Applications

`argocd/projects.yaml` defines the `platform` AppProject (destinations for `argocd`, `platform`, `platform-prod`, `monitoring`, `logging`, `security`; read-only and deployer roles). `argocd/app-of-apps.yaml` is the single root object; it deploys everything in `argocd/applications/`.

| Wave | Application | Source | Sync |
|---|---|---|---|
| -10 | platform-namespaces | `kubernetes/namespaces` | automated |
| -5 | platform-core | `kubernetes/core` | automated |
| 0 | api-gateway, user-service, product-service, notification-service, frontend | Helm charts | automated |
| 1 | order-service | Helm chart | automated |
| 2 | platform-policies | `kubernetes/policies` | automated |
| 3 | monitoring, logging | kustomize | automated |
| 10 | platform-production | `kubernetes/overlays/production` | **manual** |

```powershell
kubectl apply -f argocd/projects.yaml
kubectl apply -f argocd/app-of-apps.yaml
kubectl -n argocd get applications
```

`Synced` means live state matches Git. `Healthy` means the workloads are actually ready — the two are independent, which is why both columns matter.

## Automated sync (development)

```yaml
syncPolicy:
  automated:
    prune: true      # remove objects deleted from Git
    selfHeal: true   # revert manual cluster edits
  syncOptions: [CreateNamespace=false]
  retry: {limit: 3, backoff: {duration: 10s, factor: 2, maxDuration: 2m}}
```

## Production approval

`argocd/applications/90-production.yaml` has no `automated` block. It stays `OutOfSync` until a human with sync rights approves:

```powershell
argocd app diff platform-production
argocd app sync platform-production
```

CI adds a second gate: a GitHub Environment (`production`) with required reviewers, or the Jenkins `input` step.

## Drift detection and self-healing

```powershell
kubectl -n platform scale deployment/api-gateway --replicas=3   # outside Git
kubectl -n argocd get application api-gateway                   # OutOfSync
# selfHeal reverts to the Git-declared replica count within a reconciliation cycle
```

Default reconciliation is every 3 minutes; force it with:

```powershell
kubectl -n argocd annotate application api-gateway argocd.argoproj.io/refresh=normal --overwrite
```

## Rollback

**Preferred — Git revert:**

```bash
git log --oneline -- helm/charts/api-gateway/values.yaml
git revert <bad-commit>
git push
# Argo CD syncs the reverted commit
```

**Emergency — Argo CD history:** UI → Application → History and Rollback, or `argocd app rollback api-gateway <id>`.

**Kubernetes native:** `kubectl -n platform rollout undo deployment/api-gateway` (self-heal will re-align to Git afterwards, so use it for diagnosis, not as the final state).

## Operational checks

```powershell
kubectl -n argocd get applications -o wide
kubectl -n argocd get application platform-core -o jsonpath='{range .status.conditions[*]}{.type}: {.message}{"\n"}{end}'
kubectl -n argocd logs statefulset/argocd-application-controller --tail=50
kubectl -n argocd logs deploy/argocd-repo-server --tail=50
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `rpc error: ... unable to look up host` | repo-server DNS cannot resolve the Git host | add `hostAliases`, or use an IP/HTTPS remote |
| `unexpected EOF` on `GenerateManifest` | dumb HTTP clone attempt | use `git://` or HTTPS (not plain HTTP) |
| `resource : not permitted in project` | destination namespace or cluster-scoped kind missing from AppProject | add to `destinations` / `clusterResourceWhitelist` |
| `ComparisonError: ... file not in or below` | kustomize root restriction | move files inside the kustomization directory (`kubernetes/core`) |
| Application `Unknown` with `Missing` resources | sync never started | check `status.operationState.message`, then `argocd app sync` |
| `OutOfSync` immediately after sync | controller mutating a defaulted field | add `ignoreDifferences` for that field |
