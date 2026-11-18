# Demo recording script (≈5 minutes)

Record at 1920×1080. Keep a terminal at 16-18 pt with a dark theme and a browser at 100 % zoom. Speak the intent before each action, then let the result land for 2-3 seconds.

## Pre-flight (before recording)

```powershell
docker compose --profile observability up -d
kubectl get nodes
kubectl -n platform get pods
kubectl -n argocd get applications
curl http://localhost:18080/gateway/api/health
```

Have these tabs open: dashboard `/ops`, Grafana, Prometheus `/targets`, Argo CD UI, terminal.

## 0:00-0:30 — Problem and architecture

Show `docs/architecture.png`.

> "Companies struggle with manual deployments, configuration drift and blind operations. This platform automates delivery with GitOps and makes every deployment observable. Six services, one Kubernetes cluster, Argo CD as the delivery control plane, Prometheus and Grafana for visibility, and default-deny networking."

## 0:30-1:15 — Application running

Show the storefront (`http://localhost:13000/store`).

> "Real functionality, not stubs. I create a user, add a product, then place an order."

Create a user, then an order of 2 units. Point at the returned total and the stock value dropping by 2.

> "The order service validated the customer, priced the basket from the product service, reserved stock atomically, and asked the notification service to send a confirmation. If any later item fails, every earlier reservation is compensated."

## 1:15-2:00 — Containers and Kubernetes

Terminal:

```powershell
docker images | Select-String platform/
kubectl -n platform get deploy,pods,hpa,pdb
kubectl -n platform get pods -o wide
```

> "Seven images, all multi-stage, all running as non-root with a read-only root filesystem. Every container has startup, readiness and liveness probes, resource requests and limits, and a disruption budget. The HPA targets CPU on the gateway and the order service."

Open one Deployment YAML to show the security context and probes:

```powershell
kubectl -n platform get deploy api-gateway -o yaml | Select-String -Pattern "runAsNonRoot|readOnlyRootFilesystem|startupProbe" -Context 0,2
```

## 2:00-2:45 — GitOps with Argo CD

Open the Argo CD UI (`kubectl -n argocd port-forward svc/argocd-server 8080:443`).

> "Thirteen applications, ordered by sync waves: namespaces, then core, then services, then policies and observability. Development self-heals; production has no automated sync at all and waits for a human."

Demonstrate drift detection:

```powershell
kubectl -n platform scale deployment/api-gateway --replicas=3
kubectl -n argocd get application api-gateway
```

Show `OutOfSync`, then wait for self-heal back to the Git value.

> "I never edited Git. Argo CD detected the divergence and reverted the cluster to the declared state."

## 2:45-3:30 — Observability

Grafana → Application Performance.

> "Live metrics scraped from every service: request rate, error ratio, p50/p95/p99 latency, plus pod restarts and deployment availability from kube-state-metrics."

Switch to Prometheus `/targets` → all platform pods UP.

Open Loki in Grafana Explore:

```logql
{namespace="platform"} | json | level="ERROR"
```

> "Logs are JSON with request IDs, so one ID correlates the gateway, the order service and the notification service."

## 3:30-4:15 — Scaling and rollback

```powershell
kubectl -n platform get hpa
kubectl -n platform run load --rm -it --image=williamyeh/hey --restart=Never -- -z 90s -c 20 http://api-gateway:8000/api/products
kubectl -n platform get hpa -w
```

> "CPU utilisation rises above the 65 % target and the HPA adds replicas; when load stops, scale-down is stabilised for five minutes to avoid flapping."

If the cluster cannot scale (single node budget), say so explicitly and show the HPA targets and events instead.

Rollback:

```powershell
git log --oneline -3 -- helm/charts/api-gateway/values.yaml
git revert --no-edit <commit>
git push
kubectl -n argocd get application api-gateway -w
```

> "Rollback is a Git revert. Argo CD reconciles back to the previous revision — no manual kubectl."

## 4:15-4:45 — Security

Dashboard → Security, then terminal:

```powershell
kubectl -n platform get networkpolicy
kubectl auth can-i get secrets --as=system:serviceaccount:platform:platform-api -n platform
```

> "Default deny in both directions with explicit allow-lists. The dashboard's service account can list pods but cannot read secrets or write anything. Scans with Trivy, Checkov, Bandit and pip-audit run in CI."

## 4:45-5:00 — Delivery pipeline and close

Show `.github/workflows/ci.yml` and the deploy workflow.

> "CI runs 93 tests, builds and scans every image, and validates manifests and charts. Deployment changes image tags in Git and requires approval for production. The cluster is reconciled, never pushed to."

## Do not fake

If a component is not running (for example HPA on a saturated node, or GitHub Actions before the first push), state the limitation on camera and show the configuration or the local equivalent. Never present demo data as live — the dashboard labels it explicitly.
