# Interview Guide: Enterprise Kubernetes GitOps Platform

A working script for a senior platform / DevOps interview on this repository. 40 questions, grouped by
domain. Every answer points at a real file in this tree, because the strongest signal in an interview is
"here is where that lives and why we chose it" rather than a definition.

Use it two ways: read the two-minute pitch first so you have a spine, then rehearse the questions you
are weakest on. Do not memorise sentences - memorise the file paths and the trade-off you made.

---

## Table of contents

- [How to talk about this project in 2 minutes](#how-to-talk-about-this-project-in-2-minutes)
- [Docker and containers (Q1-Q5)](#docker-and-containers-q1-q5)
- [Kubernetes core objects (Q6-Q12)](#kubernetes-core-objects-q6-q12)
- [Services and Ingress networking (Q13-Q17)](#services-and-ingress-networking-q13-q17)
- [ConfigMaps and Secrets (Q18-Q21)](#configmaps-and-secrets-q18-q21)
- [Helm (Q22-Q25)](#helm-q22-q25)
- [GitOps and Argo CD (Q26-Q31)](#gitops-and-argo-cd-q26-q31)
- [Observability: Prometheus, Grafana, Alertmanager (Q32-Q36)](#observability-prometheus-grafana-alertmanager-q32-q36)
- [Autoscaling, rolling updates and rollbacks (Q37-Q39)](#autoscaling-rolling-updates-and-rollbacks-q37-q39)
- [Container and Kubernetes security (Q40)](#container-and-kubernetes-security-q40)
- [Common follow-up traps](#common-follow-up-traps)

---

## How to talk about this project in 2 minutes

"**What it is.** A production-shaped microservice platform: an edge API gateway, four domain services
(users, products, orders, notifications), a Postgres instance, an ops console and a platform API - all
of it deployed by Argo CD from Git, never by `kubectl` from a laptop or a CI runner.

**The applications.** Python 3.12 / FastAPI services sharing a small internal library,
`applications/shared/service_kit`, which gives every service the same probes (`/health/live`,
`/health/ready`), Prometheus metrics, structured logging and a resilient HTTP client with timeouts,
bounded retries and a per-target circuit breaker (`service_kit/http.py`). `order-service` is the
interesting one: it orchestrates a saga - validate the customer, reserve stock, compensate on failure,
persist the order, then notify - and it degrades rather than loses orders
(`applications/order-service/app/main.py`).

**Delivery.** One opinionated Helm chart, `helm/microservice`, is the template for every service; a
per-service chart under `helm/charts/*` carries the values. Kustomize overlays then shape
`kubernetes/base` into `kubernetes/overlays/development` and `kubernetes/overlays/production`.
Argo CD runs the app-of-apps pattern (`argocd/app-of-apps.yaml`), with sync waves so namespaces and
policies land before workloads. Development self-heals and prunes; production has no automated sync
block at all, so a human reviews the diff and clicks Sync (`argocd/applications/90-production.yaml`).

**Guardrails.** Namespaces run Pod Security Standards at `restricted`, containers are non-root with a
read-only root filesystem and all capabilities dropped, default-deny NetworkPolicies with explicit
allow-lists, a ResourceQuota and LimitRange per namespace, per-service PodDisruptionBudgets, and HPA
on the latency-sensitive path.

**Observability.** Prometheus scrapes annotated pods, `monitoring/prometheus/alert-rules.yml` encodes
the SLO-style alerts (5xx ratio, p95 latency, availability), and Alertmanager groups and inhibits on
`alertname`/`service`/`namespace`.

**The one sentence.** Git is the only writer to the cluster; the cluster is continuously reconciled
toward it, and every guardrail - security context, network policy, quota, PDB, probe, alert - lives in
the same reviewable diff."

If they only remember three things: probe semantics are deliberate, production is a manual gate, and
the guardrails are code, not tribal knowledge.

---

## Docker and containers (Q1-Q5)

### Q1. Walk me through what happens when you build the gateway image.

`applications/api-gateway/Dockerfile` is a two-stage build. The `builder` stage is `python:3.12-slim`,
creates a venv at `/opt/venv`, installs `applications/api-gateway/requirements.txt` with
`PIP_NO_CACHE_DIR=1`, then the venv is copied into the `runtime` stage as a single layer. The runtime
stage creates a real user `app` with a fixed `--uid 10001 --gid 10001`, copies `applications/shared`
and the service's `app/` directory with `--chown=10001:10001`, and switches to `USER 10001:10001`
before `EXPOSE`/`CMD`. The build context is the repository root (`docker build -f applications/api-gateway/Dockerfile .`)
because the image needs `applications/shared`, and `.dockerignore` keeps `.venv`, `node_modules` and
the frontend `dist` out of the context. The payoff: no compiler toolchain, no pip cache and no root user
in the final image, and one venv layer shared across the four services that install similar deps.

### Q2. Why does the image use a fixed UID, and what is your stance on image tags?

The fixed UID matters because Kubernetes `runAsNonRoot: true` has to *prove* the user is non-root; a
numeric USER is verifiable at admission time, a name is not always. It also makes
`securityContext.runAsUser: 10001` in `kubernetes/base/api-gateway.yaml` a no-op confirmation rather
than a surprise, and it lines up with `fsGroup: 10001` so any mounted volume is group-writable by the
app. On tags: `1.0.0` is only a *label*. Mutable tags are the enemy of rollback - if `1.0.0` is
repushed, the same manifest is now a different image. The honest answer is that this repo pins tags and
a real production setup should promote by digest (`image@sha256:...`) or use an immutable tag scheme
like a commit SHA, which is what the deploy workflow defaults to (`image_tag` falls back to
`github.sha` in `.github/workflows/deploy.yml`). Treat "the tag is a constant" as a policy you enforce
in the registry (tag immutability), not a hope.

### Q3. The compose file has `healthcheck` and `deploy.resources.limits`. Do those translate to Kubernetes?

Not literally, and it is worth being precise. `docker-compose.yml` healthchecks are the local
equivalent of probes - e.g. the gateway's check hits `http://127.0.0.1:8000/health/ready` with a
Python one-liner, `start_period: 20s`, `retries: 5`. `depends_on: {condition: service_healthy}` then
gives you start-up ordering that Kubernetes deliberately does not give you. Compose V2 does honour
`deploy.resources.limits` for `cpus`/`memory`, but there is no equivalent of a Kubernetes *request* -
no scheduler reservation, no QoS class - so the compose file is a rough approximation of the cluster,
not a description of it. That is exactly why the real resource contract lives in the manifests
(`requests: {cpu: 50m, memory: 96Mi}`) and not in compose.

### Q4. Why does the image ship a HEALTHCHECK at all if Kubernetes ignores it?

Kubernetes ignores `HEALTHCHECK` completely - it runs its own probes - but the directive still earns its
place for `docker run`, compose and any scanner that reports image metadata. The implementation detail
is deliberate: `python:3.12-slim` has no `curl`, so the check is
`python -c "import urllib.request; ..."` against `/health/live`, with `--start-period=15s`. The bigger
point for the interview: the *contract* is the endpoint, and both runtimes consume the same endpoint.
`/health/live` means "the process is up and the event loop is turning" - it must never check a
dependency, or a Postgres blip becomes a restart storm. `/health/ready` means "I can serve traffic" and
in `order-service` it is `db.ping()` (`applications/order-service/app/main.py`).

### Q5. How do you keep builds fast and reproducible across six services?

Layer ordering does most of the work: requirements are copied and installed before application code, so
a code change does not invalidate the dependency layer. All services build from the repo root so they
share the same `applications/shared` copy step and the same `.dockerignore`. Reproducibility comes from
pinning - base image tag, `requirements.txt` versions, and `dependabot.yml` at the repo root raising PRs
for both rather than silent drift. The CI path lints Helm and renders manifests before any image is
built (`.github/workflows/deploy.yml`, `verify` job), so a broken template fails in seconds instead of
after a five-minute build.

---

## Kubernetes core objects (Q6-Q12)

### Q6. When do you reach for a StatefulSet instead of a Deployment?

When identity matters: stable network name, stable storage, ordered lifecycle. `kubernetes/base/postgres.yaml`
is the StatefulSet - `serviceName: postgres`, a `volumeClaimTemplate` requesting `1Gi` `ReadWriteOnce`
on the `standard` storage class, and `PGDATA=/var/lib/postgresql/data/pgdata` so the initdb files sit in
a subdirectory of the mount instead of colliding with `lost+found`. Everything stateless - gateway,
users, products, orders, notifications, frontend, platform-api - is a Deployment, because replicas are
interchangeable and can be replaced in any order. A good answer adds the caveat: strictly, a
StatefulSet's `serviceName` should point at a *headless* Service (`clusterIP: None`) to get per-pod DNS
like `postgres-0.postgres`; ours is a normal ClusterIP, which is fine for a single replica but would not
give you stable per-pod addressing if you scaled it.

### Q7. Explain the three probes as they are configured here - and what each failure actually does.

`startupProbe` hits `/health/live` every 3s with `failureThreshold: 30`, which buys roughly 90 seconds
of boot budget before anything else is judged; while it is failing, the liveness and readiness probes do
not run and the container is not killed. `livenessProbe` hits `/health/live` every 15s - failure means
the kubelet *kills and restarts the container*, so it must only test the process itself. `readinessProbe`
hits `/health/ready` every 5s - failure means the pod is *removed from the Service endpoints*, no restart,
which is how you drain a pod that has lost its database without a crash loop. The asymmetry matters:
put a dependency check in liveness and one flaky Postgres takes the whole deployment down in a restart
loop; put nothing in readiness and you serve 500s. The implementation is in
`applications/shared/service_kit/app_factory.py`, where `/health/ready` wraps the check in
`asyncio.wait_for(..., timeout=3.0)` and returns 503 rather than throwing.

### Q8. Requests versus limits - what QoS class do these pods get, and does it matter?

Requests are what the scheduler reserves and what HPA percentages are computed against; limits are the
cgroup ceiling. `kubernetes/base/api-gateway.yaml` sets `requests: {cpu: 50m, memory: 96Mi}` and
`limits: {cpu: 500m, memory: 256Mi}`; because requests do not equal limits, the pod is **Burstable**, not
Guaranteed. That is a deliberate trade: a 10x CPU burst headroom for a service that is idle most of the
time, at the cost of being a candidate for eviction under node memory pressure. Only `requests == limits`
for both CPU and memory gives Guaranteed; no requests and no limits gives BestEffort, which is what you
never want for anything customer-facing. Note the CPU limit also causes throttling - if you see p95
latency with low average utilisation, CFS throttling is the first thing to check, which is exactly what
the `HighCPUUsage` alert at 85% of limit is pointing at.

### Q9. Walk me through the ResourceQuota and LimitRange and how they interact.

`kubernetes/policies/resource-governance.yaml` defines `platform-quota` in namespace `platform`:
`requests.cpu: 4`, `requests.memory: 6Gi`, `limits.cpu: 8`, `limits.memory: 10Gi`, `pods: 40`,
`loadbalancers: "0"`, plus object counts for Deployments and StatefulSets. The LimitRange
`platform-defaults` supplies `default` limits of `250m`/`256Mi`, `defaultRequest` of `25m`/`64Mi`, and a
per-container `max` of `2` CPU / `1Gi` memory. They interact in a specific order: at admission the
LimitRange defaults are applied first, *then* quota is evaluated - which is why quota can be enforced
even for a manifest that forgot to set requests. The interesting one is `loadbalancers: "0"`: nobody can
accidentally create a cloud LoadBalancer and start paying for it, so all external traffic must enter
through the in-cluster ingress controller.

### Q10. Why the `app.kubernetes.io/*` labels, and what is the trap with selectors?

They are the standard recommended labels: `name`, `component`, `part-of`, `managed-by`, `instance`,
`version`. They are consistent across `kubernetes/base/*.yaml`, the Helm helpers
(`helm/microservice/templates/_helpers.tpl`) and the Prometheus relabeling, which reads
`__meta_kubernetes_pod_label_app_kubernetes_io_name` into the `service` label - so the label you set in
the manifest is the label on your dashboards. The trap: a Deployment's `spec.selector` is **immutable**
after creation. That is why the chart keeps two helpers - `microservice.labels` (rich, changes freely)
and `microservice.selectorLabels` (name + instance, effectively frozen). If you add a label to the
selector you must delete and recreate the Deployment, which in a GitOps repo means a pruning sync, not a
rolling update.

### Q11. What do the namespaces do for you beyond isolation of names?

They carry the Pod Security admission labels. `kubernetes/namespaces/namespaces.yaml` enforces
`restricted` on `platform` and `platform-prod`, and `baseline` on `monitoring`, `logging`, `argocd` and
`security` (with `warn: restricted` so you still see what would break). That is a real control, not
documentation: a pod that tries `privileged: true` or omits `runAsNonRoot` in `platform` is *rejected at
admission*. Namespaces also scope the quota, the NetworkPolicies, the RBAC Roles and the Argo CD
destinations. The reason monitoring is only `baseline` is honest engineering: node-exporter and some
exporters legitimately need host access, and pretending otherwise just pushes people to disable PSA
everywhere.

### Q12. A pod in this platform is Pending or CrashLoopBackOff. How do you actually debug it?

For Pending, `kubectl -n platform describe pod` and read the events: in this cluster the usual causes are
quota exhaustion (`exceeded quota: platform-quota`), a resource request larger than any node's
allocatable, or a PVC that cannot bind. `kubectl get resourcequota -n platform` shows used vs hard
immediately. For CrashLoopBackOff, `kubectl logs --previous` is the first command, because the current
container has usually restarted past the interesting output; then check whether it is a liveness kill
(exit code 137) versus an application exception. In this repo the alerts already encode the two
patterns - `PodCrashLooping` fires on more than 3 restarts in 15 minutes, `PodNotReady` on 10 minutes
Pending/Unknown - so the alert that paged you tells you which branch to take. The `order-service` has one
extra gotcha: it retries the DB at startup (`db.init_models(retries=..., delay=2.0)`), so a slow
Postgres looks like a long startup, not a crash - the `startupProbe` budget exists for exactly that.

---

## Services and Ingress networking (Q13-Q17)

### Q13. Why is every Service in this repo `ClusterIP`, and how does traffic get in from outside?

Because the only intended external entry point is the Ingress controller. `kubernetes/base/api-gateway.yaml`,
`postgres.yaml` and the rest all declare `type: ClusterIP`, and the quota forbids LoadBalancers outright
(`loadbalancers: "0"` in `resource-governance.yaml`). External traffic hits the kind node's mapped host
ports - `extraPortMappings: 80 -> 18080` and `443 -> 18443` in `kubernetes/kind-config.yaml` - which the
NGINX ingress controller picks up, and the Ingress then routes to ClusterIP Services. The interview point:
a `NodePort` or `LoadBalancer` per service would mean six public entry points, six TLS stories and six
things to firewall; one Ingress means one place to terminate TLS, one place for rate limits, one place to
audit. `kubectl port-forward` remains the escape hatch for debugging, and that is granted explicitly via
`pods/portforward` in the `platform-developer` Role.

### Q14. What decides whether a pod receives traffic, and what breaks that chain?

Endpoints. The Service selector matches pod labels, but only pods whose **readiness** gate passes are
published as EndpointSlices and receive traffic through kube-proxy. So the chain is:
`readinessProbe` -> EndpointSlice membership -> Service -> pod. Three things break it in practice: a
selector that does not match the pod labels (a typo in `app.kubernetes.io/name`), a readiness probe that
never passes, and a NetworkPolicy that silently drops the traffic after it has been routed. That last one
is the nasty case - the Service looks healthy, `kubectl get endpoints` is populated, and the connection
still times out, because the packet was dropped by the CNI. Our `allow-gateway-to-services` policy in
`kubernetes/policies/network-policies.yaml` is what makes that possible at all, so it is the first place
to look when a Service "exists but does not answer".

### Q15. Explain `rewrite-target: /$2` in the Ingress - why is it written that way?

`kubernetes/base/ingress.yaml` uses `nginx.ingress.kubernetes.io/use-regex: "true"` with
`rewrite-target: /$2` and paths like `/platform(/|$)(.*)`. The first capture group is the delimiter
(`/` or end of string), the second is the rest of the path, so `/platform/api/health` becomes `/api/health`
before it reaches `platform-api:8080`. The `(/|$)` part is what makes the bare `/platform` (no trailing
slash) still match - without it you get a 404 on exactly the URL people type first. Paths are
`ImplementationSpecific` so NGINX applies its own longest-prefix ordering: `/platform...` and `/gateway...`
beat the catch-all `/()(.*)` that sends everything else to `frontend:80`. The trade-off is honest: regex
rewriting is NGINX-specific, so this Ingress does not port cleanly to another controller; a Gateway API
`HTTPRoute` with `URLRewrite` filters would be the vendor-neutral version.

### Q16. How is TLS handled, and what is different in the production overlay?

In the base, TLS is not terminated at the Ingress at all - it is an HTTP-only local demo. The production
overlay patches it on: `kubernetes/overlays/production/kustomization.yaml` adds
`nginx.ingress.kubernetes.io/ssl-redirect: "true"` via a JSON6902 patch (note the `~1` escaping for the
`/` inside the annotation key, which is a classic Kustomize gotcha). What is still missing for real TLS is
a `spec.tls` block plus a certificate source - cert-manager with a `ClusterIssuer`, or a pre-created
Secret. The reason to state that out loud in an interview: `ssl-redirect: true` without a certificate
gives you a redirect to a port that cannot complete a handshake, which is worse than plain HTTP. The
kind cluster does map host port 18443, so the plumbing exists; the certificate lifecycle is the remaining
gap.

### Q17. A client gets a 502 from the ingress. Give me your triage order.

First, is it the ingress or the app? `kubectl -n ingress-nginx logs` will say `connect: connection refused`
or `no endpoints available` versus `upstream timed out`, and those are different problems. Second,
`kubectl -n platform get endpoints <service>` - empty means the selector or the readiness gate is wrong.
Third, port alignment: our Services name the port `http` and the Ingress references `number: 8000`, but a
mismatch between the Service `targetPort` and the container's `containerPort` name is a silent black hole.
Fourth, NetworkPolicy: `allow-ingress-controller` explicitly allow-lists the `ingress-nginx` namespace for
ports 8000/8080 on `frontend`, `api-gateway` and `platform-api` - if the controller runs in a different
namespace, the label `kubernetes.io/metadata.name: ingress-nginx` no longer matches and every request
times out. A 504 instead of 502 usually means the upstream accepted the connection and was too slow,
which points at `proxy-read-timeout` or at an application-level cascade - and in this platform that is
often the gateway's own 2.5s timeout surfacing as a slow upstream.

---

## ConfigMaps and Secrets (Q18-Q21)

### Q18. How does configuration reach the containers, and what happens when you change it?

Two paths. Non-sensitive config is `platform-config` (`kubernetes/base/configmap.yaml`), consumed wholesale
with `envFrom: configMapRef` in `kubernetes/base/api-gateway.yaml`, which gives the app `APP_ENV`,
`LOG_LEVEL`, the four service URLs, `REQUEST_TIMEOUT_SECONDS`, `RATE_LIMIT_PER_MINUTE` and the
observability endpoints as environment variables. The critical caveat: **environment variables are
snapshotted at container start**. Editing the ConfigMap changes nothing in a running pod, and Argo CD
syncing the new ConfigMap does not restart anything either - the pod keeps serving the old values until
something recreates it (usually the next deploy). The production fix is a checksum annotation of the
ConfigMap content on the pod template, or `kubectl rollout restart` as the manual equivalent. Files
mounted as volumes behave differently - the kubelet syncs them on a delay - which is why `postgres-init`
is mounted as a volume rather than read from env: it is a file, and it is only read at initdb time.

### Q19. Are Kubernetes Secrets actually secret?

Not by themselves. A Secret is base64-encoded, not encrypted; anyone with `get` on `secrets` in the
namespace reads it in plain text, and anyone with etcd access reads it unless encryption-at-rest is
configured. This repo handles that honestly: `kubernetes/base/secret.example.yaml` is a placeholder with
`REPLACE_ME` values and a comment saying "never in Git", and the real `platform-secrets` is created
out-of-band with `kubectl create secret generic` (documented in the file header, scripted in
`scripts/create-dev-secrets.ps1`). For a real environment the answer is External Secrets Operator pulling
from a vault, or Sealed Secrets / SOPS so the encrypted blob can live in Git and still be GitOps. The
minimum bar I would insist on: encryption at rest for Secrets in etcd, RBAC that does not grant `secrets`
to application service accounts, and secrets never in a ConfigMap or an image layer.

### Q20. In the Helm chart, why are secret-backed env vars emitted before plain ones?

Because of how Kubernetes expands `$(VAR)` in env values: expansion only works against variables defined
*earlier in the same `env` list*. `helm/microservice/templates/deployment.yaml` has an explicit comment
about it and ranges over `.Values.secretEnv` first, then `.Values.env` - so a `DATABASE_URL` of
`postgresql://platform:$(POSTGRES_PASSWORD)@postgres:5432/orders` resolves correctly. Two traps worth
knowing: variables injected via `envFrom` are **not** available for `$(VAR)` expansion in `env`, and a
literal `$` in a value will be mangled unless you escape it as `$$`. Preferring `secretKeyRef` per key over
`envFrom: secretRef` is also deliberate - it keeps the blast radius to the keys the service actually
needs, and it makes the dependency visible in the Deployment spec.

### Q21. How do you rotate a credential in this setup without downtime?

The honest answer is "rotation is a deploy". Update the Secret (in the vault, or with
`kubectl create secret ... --dry-run=client -o yaml | kubectl apply -f -`), then roll the consumers,
because env vars only refresh on container start. Sequence matters: for `POSTGRES_PASSWORD` you must
rotate the database user first (or add the new password alongside), then the Secret, then restart the
services - otherwise `order-service` comes up against a password that no longer works and its readiness
probe correctly refuses traffic for as long as the mismatch lasts. The failure mode is graceful rather
than catastrophic here because readiness is `db.ping()` and the services retry DB init at startup. The
design improvement I would argue for: mount the credential as a file and watch it, or use a sidecar/CSI
driver, so rotation does not require a pod restart at all.

---

## Helm (Q22-Q25)

### Q22. Why one shared chart plus per-service charts instead of one chart per service?

`helm/microservice` is the contract: it renders Deployment, Service, ServiceAccount, HPA and PDB from
values, and its defaults are deliberately safe (non-root, read-only root filesystem, dropped
capabilities, bounded resources, all three probes). `helm/charts/<service>/` is that chart plus a
`values.yaml` carrying the service-specific bits - image repository, port, extra env, secret refs. The
benefit is that a security fix (say, `automountServiceAccountToken: false`) lands once and every service
inherits it; the cost is that per-service oddities become values rather than code, and values files can
grow into a second, worse configuration language. If a service ever needs genuinely different topology -
a worker with no Service, a cron job - I would rather it get its own chart than bolt three `if`s into the
shared one. CI enforces that all of them stay renderable: `helm lint` on every chart and
`helm template ... > /dev/null` in the `verify` job of `.github/workflows/deploy.yml`.

### Q23. Explain the helpers - and why `labels` and `selectorLabels` are separate.

`helm/microservice/templates/_helpers.tpl` follows the standard convention:
`microservice.fullname` uses `fullnameOverride`, otherwise `Release.Name`-prefixed unless the release name
already contains the chart name, and everything is `trunc 63 | trimSuffix "-"` because 63 characters is the
label-value limit. `microservice.labels` is the rich set (`helm.sh/chart`, `name`, `instance`, `version`,
`managed-by`, `part-of`), while `microservice.selectorLabels` is only `name` + `instance`. They are separate
because selectors are immutable: if you put a chart-version label into the selector, every `helm upgrade`
that bumps the chart version becomes a failed in-place update. The `part-of: gitops-platform` label in the
rich set is also what lets `kubectl -n platform get all -l app.kubernetes.io/part-of=gitops-platform` work
across all services.

### Q24. How do the values handle the "replicas vs HPA" conflict?

`helm/microservice/templates/deployment.yaml` wraps `replicas:` in `{{- if not .Values.autoscaling.enabled }}`.
That is the important line: if the HPA owns replica count, the Deployment must not declare one, otherwise
every `helm upgrade`/Argo sync resets the count and the HPA immediately fights it back - you get flapping
replica counts and confusing `ScalingActive` events. The chart's `autoscaling` block defaults to
`enabled: false` with `minReplicas: 2`, `maxReplicas: 6`, `targetCPUUtilizationPercentage: 70`, and
`behavior: {}` so the default HPA has no custom scaling policy. Note that in `argocd/applications/10-api-gateway.yaml`
the Application sets `replicaCount: 1` and `image.tag: "1.0.0"` inline via `helm.values`, i.e. the overlay
of overlays is the Argo Application itself - which is convenient, and also the thing to check first when
a rendered manifest disagrees with the values file.

### Q25. How do you validate a chart change before it reaches a cluster?

Three layers, all cheap. `helm lint` catches template syntax, missing values and bad indentation.
`helm template <release> <chart> --namespace platform` renders the full manifest so you can diff it - and
this repo has `tests/test_helm_charts.py` doing chart-level assertions so regressions fail in pytest, not
in the cluster. Then `kubeconform`/`kubectl apply --dry-run=server` against a real API server catches
schema and admission errors, which is the only way to see PSS `restricted` rejections or quota denials
before they hit a live namespace. What we deliberately do *not* do is `helm upgrade` from CI: Argo CD is
the only writer, so the pipeline's job is to commit a new tag and let reconciliation happen
(`.github/workflows/deploy.yml` never calls `helm install` or `kubectl`). The exception is `helm diff`
locally, which is the fastest way to answer "what is Argo about to change".

---

## GitOps and Argo CD (Q26-Q31)

### Q26. Describe the app-of-apps structure and the sync-wave ordering.

`argocd/app-of-apps.yaml` is a single Application whose source path is `argocd/applications` with
`directory.recurse: true` - so the "app" it deploys is a directory of other Application objects. Sync that
one object and Argo CD creates the rest, which then each reconcile their own path. Ordering comes from
`argocd.argoproj.io/sync-wave` annotations within a wave: `00-namespaces` first, then `01-core`, then the
service Applications at wave `0`, `20-policies` at wave `2`, monitoring and logging after that, and
`90-production` last at wave `10`. Waves are ordered ascending, and Argo waits for a wave to be healthy
before starting the next - which is why the Namespace objects and their PSS labels exist before any pod
tries to be admitted into them. The app-of-apps itself has `retry: {limit: 5, backoff: {duration: 10s,
factor: 2, maxDuration: 3m}}`, so a transient API-server hiccup during bootstrap self-corrects instead of
leaving a half-built platform.

### Q27. What exactly do `selfHeal` and `prune` do, and where do you turn them off?

`prune: true` means: a resource that Argo CD previously applied and that is no longer in Git gets
**deleted** from the cluster. `selfHeal: true` means: if the live object drifts from the rendered
manifest - someone `kubectl edit`s a replicas count, or a controller mutates a field - Argo reverts it on
the next reconciliation. Development services have both on (`argocd/applications/10-api-gateway.yaml`:
`automated: {prune: true, selfHeal: true}`), and `argocd/applications/90-production.yaml` has **no
`automated` block at all**, so it stays `OutOfSync` until a human syncs. That is the entire production
control: not a different pipeline, just the absence of automation, which makes the diff reviewable and the
sync a recorded event. The operational consequence to be honest about: with `selfHeal` on, `kubectl edit`
is not a debugging tool, it is a fight you lose in about three minutes - use `kubectl scale` on a
temporary basis only, or expect Argo to undo it mid-investigation.

### Q28. What is the AppProject actually restricting?

`argocd/projects.yaml` defines project `platform` with `sourceRepos: ["*"]` (documented as a convenience
for forks - in a real org this is the field you lock down first), a destination allow-list of the five
namespaces plus `platform-prod` on the in-cluster API, a `clusterResourceWhitelist` limited to Namespace,
ClusterRole, ClusterRoleBinding and NetworkPolicy, and two roles: `read-only` (get on applications) and
`deployer` (sync + get). Project-level RBAC is what stops an application from deploying into `kube-system`
or creating a ClusterRole it should not. One nuance worth raising yourself before they do: the project also
blacklists namespace-scoped `ResourceQuota` and `LimitRange`, while
`kubernetes/policies/resource-governance.yaml` defines exactly those kinds - in Argo a blacklisted kind is
not synced or diffed by project applications, so those guardrails depend on an out-of-band apply or a
separate project. Verify with `argocd app diff platform-policies` rather than assuming; flagging it as a
known gap is a better answer than claiming the quota is enforced by the app that cannot manage it.

### Q29. Why does every Application carry the resources finalizer?

`finalizers: [resources-finalizer.argocd.argoproj.io]` makes deletion cascade: deleting the Application
deletes the resources it manages, instead of orphaning them in the cluster. Without it you get the classic
GitOps mess - the app is gone from Argo, the Deployments keep running, and nobody knows who owns them.
The flip side is that cascade deletion is destructive and blocking: if a finalizer hangs because a
resource cannot be deleted (a namespace stuck in `Terminating`, an unresponsive CRD), the Application sits
in `Deleting` forever and you have to go remove the finalizer by hand. That is the reason production
promotion is a separate Application rather than the same object with a different overlay: you can delete
the dev app without touching production.

### Q30. Where does the image tag come from, and where are the approval gates?

The pipeline never talks to the cluster. `.github/workflows/deploy.yml` has a `verify` job (lint + render
every chart), an `update-dev` job that rewrites `tag:` in `helm/charts/*/values.yaml` and commits, and an
`update-prod` job that only runs on manual `workflow_dispatch` into the `production` GitHub Environment -
which is where required reviewers live. So there are two human gates that are independent: the GitHub
Environment approval on the commit, and the Argo CD manual sync on the cluster. The commit message is
generated (`chore(deploy): promote <tag> to development`), the bot identity is explicit
(`gitops-bot`), and `concurrency` is keyed per environment with `cancel-in-progress: false` so two
promotions cannot interleave and leave a half-updated values file. That "commit changes desired state,
reconciler changes actual state" split is the whole argument for GitOps in one sentence.

### Q31. How do you roll back, and why is `argocd rollback` not the default answer?

Preferred: `git revert` the bad commit. That restores the previous desired state, keeps the audit trail
linear, and Argo reconciles toward it - the rollback is itself reviewed and reproducible, and it works even
if the Argo CD UI is down. `argocd app rollback <app> <id>` is faster for an incident, because it replays a
previous synced revision without a commit, but it leaves Git and the cluster disagreeing until someone
opens the revert PR - and with `selfHeal: true`, the next sync of the reverted-to state can undo it. At the
Deployment level, `kubectl rollout undo` works only as far back as `revisionHistoryLimit: 5` (set in
`kubernetes/base/api-gateway.yaml` and the chart) allows ReplicaSets to be retained. My rule: click rollback
to stop the bleeding, open the revert PR in the same five minutes, and never let the temporary divergence
survive the incident.

---

## Observability: Prometheus, Grafana, Alertmanager (Q32-Q36)

### Q32. How are the application metrics designed, and what protects you from cardinality blowup?

`applications/shared/service_kit/metrics.py` instruments every service with `http_requests_total`
(`service`, `method`, `path`, `status`), a latency histogram with buckets from 5ms to 10s, an in-progress
gauge, and a `service_up` gauge driven by readiness. The cardinality protection is the key detail:
`_route_template()` reads `request.scope["route"].path`, which is the *FastAPI route template*
(`/orders/{order_id}`), not the raw URL - so a thousand distinct order IDs produce one label value, not a
thousand. Unmatched requests collapse to `"unmatched"`. `/metrics` and `/health/live` are excluded from
instrumentation so scrape and probe traffic do not pollute the request rate. This is also why the alert
expressions work at all: `sum by (service)` is meaningful only because the label set is bounded.

### Q33. How does Prometheus find the pods, and why not just static targets?

`monitoring/prometheus/prometheus.yml` uses `kubernetes_sd_configs: [{role: pod}]` with a relabel chain:
keep pods annotated `prometheus.io/scrape: "true"`, take `__metrics_path__` from
`prometheus.io/path`, and rewrite `__address__` to `<pod-ip>:<prometheus.io/port>`. It then attaches
`namespace`, `pod`, and - importantly - `service` from `app.kubernetes.io/name` and `component` from
`app.kubernetes.io/component`. So the annotation set in the chart (`podAnnotations` in
`helm/microservice/values.yaml`) is the opt-in, and scaling to five replicas needs no config change: pods
appear and disappear and the target list follows. Node-exporter and kube-state-metrics get their own jobs
with namespace-scoped discovery, and kubelet/cAdvisor is scraped through the node proxy for container CPU
and memory. The failure mode to name: if a pod forgets the annotation it is invisible, and you find out
because `ServiceDown` never fires for it - silence is not health.

### Q34. Justify the thresholds in `alert-rules.yml`. Which of these would you actually page on?

The rules are ratio-and-duration based, which is the point. `HighErrorRate` fires when the 5xx share of
requests exceeds 5% for 5 minutes, with `clamp_min(..., 0.001)` on the denominator so a near-idle service
does not divide by zero and alert on one failed request. `HighLatencyP95` uses
`histogram_quantile(0.95, sum by (le, service) (rate(..._bucket[5m]))) > 1` - p95 above one second, and
the `sum by (le, service)` is what makes the quantile valid across replicas (never average percentiles).
`ServiceDown` is `up{job="platform-pods"} == 0` for 2 minutes; `DeploymentUnavailable` fires below 50%
available for 5 minutes, which catches "deployed but not serving" in a way replica counts do not.
`PodCrashLooping` is `increase(kube_pod_container_status_restarts_total[15m]) > 3`, `PodNotReady` is 10
minutes Pending/Unknown, and the resource alerts fire at 85% of the container limit for 10 minutes. What I
would page on: `ServiceDown`, `HighErrorRate`, `DeploymentUnavailable`, `NodeMemoryPressure`. What I would
ticket: `HighLatencyP95` alone, `PVCAlmostFull` at 15% free, `HighMemoryUsage`, `HighCPUUsage` - those are
capacity signals, and paging on them trains people to ignore the pager.

### Q35. What does Alertmanager add that Prometheus alerting rules do not?

Routing, grouping, inhibition and delivery state. `monitoring/alertmanager/alertmanager.yml` groups by
`alertname`, `service`, `namespace` with `group_wait: 15s`, `group_interval: 5m` and
`repeat_interval: 4h`, with a child route for `severity="critical"` that waits only 5s and repeats hourly.
The inhibition rule is the valuable one: a critical alert suppresses warnings with the same
`service`/`namespace`, so one dead service produces one notification instead of six correlated ones. The
receiver is `ui-only` by design - no external endpoint is configured, so the platform works offline and the
alerts are still inspectable at `:9093`; swapping in a webhook or PagerDuty receiver is a one-block change.
Honest limitation to state: with no real receiver, this is detection without delivery, and
`resolve_timeout: 5m` means a flapping alert stays "firing" between blips rather than resolving instantly.

### Q36. Grafana is provisioned, not clicked. Why does that matter?

Because a dashboard that only exists in one person's browser is not monitoring, it is a screenshot. The
JSON files under `monitoring/grafana/dashboards/` are mounted and loaded by
`monitoring/grafana/provisioning/dashboards/dashboards.yml` with the Prometheus datasource provisioned
alongside; `GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH` makes `platform-overview.json` the landing page.
Dashboard changes therefore go through the same review as code, and a rebuild or a new cluster gets the
same view with no manual import. The compose stack sets `GF_AUTH_ANONYMOUS_ENABLED: "true"` with role
Viewer and `GF_USERS_ALLOW_SIGN_UP: "false"` - acceptable for a local demo on localhost, and something I
would explicitly call out as *not* the production configuration. The dashboards themselves are organised
by question: cluster overview, node health, pod health, deployment monitoring, API latency,
application performance.

---

## Autoscaling, rolling updates and rollbacks (Q37-Q39)

### Q37. What does the HPA actually need, and how is `api-gateway` configured?

It needs the metrics API - `metrics-server` in-cluster - because the controller reads pod CPU from
`metrics.k8s.io`; without it the HPA reports `unknown` for the metric and never scales, which is the single
most common "HPA is broken" cause. It also needs **requests** on every container, because
`averageUtilization` is a percentage *of the request*: 65% of `50m` is `32.5m` per pod, not 65% of the
node. `kubernetes/policies/resource-governance.yaml` sets `api-gateway` to `minReplicas: 2`,
`maxReplicas: 6`, target 65% CPU, with `behavior` adding a 300s scale-down stabilization window and a 50%
per-60s scale-down policy, plus a 30s scale-up window allowing 2 pods per 60s - fast up, slow down, which
is the right asymmetry for latency-sensitive traffic. `order-service` targets 70% with only a scale-down
window, and the production overlay raises the ranges to 3-10 and 3-8. The default 10% tolerance means the
HPA ignores small fluctuations rather than chasing them.

### Q38. Walk me through a rolling update of the gateway with these settings.

`strategy: RollingUpdate` with `maxSurge: 1, maxUnavailable: 0` (both in
`kubernetes/base/api-gateway.yaml` and `helm/microservice/values.yaml`). A new ReplicaSet is created, one
extra pod is added, and the rollout proceeds only when that pod is **Ready** - zero unavailable at all
times, which is why readiness has to be honest: a readiness probe that returns 200 during warmup turns
"zero downtime" into "zero downtime, full of 503s". `maxUnavailable: 0` costs surge capacity, so with the
quota's `requests.cpu: 4` you must leave headroom for one extra pod per service or the new pod sits
Pending and the rollout stalls. Termination is graceful in the other direction: `preStop: sleep 5` gives
kube-proxy and the ingress time to remove the endpoint before the process exits, and
`terminationGracePeriodSeconds: 30` bounds the wait before SIGKILL. `progressDeadlineSeconds` defaults to
600s, so a genuinely stuck rollout surfaces as `ProgressDeadlineExceeded` rather than hanging forever.

### Q39. Rollout is failing halfway. What do you look at, and how do you get back?

`kubectl -n platform rollout status deployment/api-gateway` tells you whether it is progressing;
`kubectl describe` shows `ProgressDeadlineExceeded` and the ReplicaSet events; `kubectl get pods -l
app.kubernetes.io/name=api-gateway` shows old and new pods side by side, and `kubectl logs <new-pod>
--previous` is where the real error is. If the new pods are Pending rather than crashing, it is capacity
or quota, not the image. To recover, `kubectl rollout undo deployment/api-gateway` returns to the previous
ReplicaSet - available because `revisionHistoryLimit: 5` keeps them - and `--to-revision` goes further back.
In this repo, though, the durable fix is the Git revert, because the next Argo sync will happily roll the
bad commit forward again; `kubectl rollout undo` is triage, not resolution. The signal that this was
designed for: `DeploymentUnavailable` fires at under 50% availability for 5 minutes, which is exactly the
window where a stuck rollout is still cheap to abort.

---

## Container and Kubernetes security (Q40)

### Q40. Take me through the security posture end to end - and name what is still missing.

Four layers. **Admission:** namespaces in `kubernetes/namespaces/namespaces.yaml` enforce Pod Security
Standards `restricted` (platform, platform-prod), `baseline` for monitoring/logging/argocd/security - so a
privileged or root pod is rejected, not just discouraged. **Pod spec:** `runAsNonRoot: true`,
`runAsUser/Group: 10001`, `seccompProfile: RuntimeDefault`, `allowPrivilegeEscalation: false`,
`readOnlyRootFilesystem: true` with an `emptyDir` at `/tmp` for anything that must write, `capabilities:
drop: ["ALL"]`, and `automountServiceAccountToken: false` because these apps never call the Kubernetes API.
**Authorization:** `kubernetes/policies/rbac.yaml` grants verbs deliberately -
`platform-deployer` gets `get/list/watch` on pods, deployments, replicasets, services and configmaps,
`patch/update` on deployments only (no `delete`, no `secrets`), and `get/list` on `pods/log`;
`platform-developer` gets read-only across the workload APIs plus `create` on `pods/portforward` and
`pods/log`. Note the verb precision: `update` is not `patch`, `list` on secrets is as dangerous as `get`,
and `escalate`/`bind` on roles is how privilege escalation usually happens.
**Network:** default-deny ingress and egress in `kubernetes/policies/network-policies.yaml`, with
allow-lists for DNS to kube-system on 53, ingress-nginx to the three public services, gateway-to-services,
order-to-dependencies, services-to-postgres, and monitoring scrape. **Supply chain:** non-root images built
from a digest-pinnable base, `dependabot.yml` for dependency updates, and the scanning workflow in
`.github/workflows/security.yml`. What is missing and I would say so: no image signature verification
(cosign/Kyverno), no admission policy beyond PSS (no Gatekeeper constraints on registries or required
labels), `sourceRepos: ["*"]` in the AppProject, TLS termination still pending in the base overlay, and
no `secrets` RBAC restriction beyond namespace scoping.

---

## Common follow-up traps

Five answers that sound right and are wrong. Getting these crisp is usually what separates a senior
candidate from a good one.

### Trap 1: "A failing readiness probe restarts the container."

No. Readiness failure only removes the pod from the Service endpoints (EndpointSlice), so it stops
receiving traffic while it stays running - that is the whole point, and it is how you survive a lost
database dependency without a restart storm. **Liveness** failure restarts the container. **Startup**
failure restarts it too, but while the startup probe is failing, liveness and readiness are not evaluated
and the container is not killed by them. In this repo `/health/live` never touches a dependency and
`/health/ready` is `db.ping()` - swap them and a Postgres blip becomes a fleet-wide crash loop.

### Trap 2: "The HPA scales on CPU, so it works out of the box."

It needs `metrics-server` (or a custom/external metrics adapter) for `metrics.k8s.io`, and it needs
`resources.requests` on every container, because `averageUtilization` is a percentage of the request. Miss
either and the HPA shows `<unknown>` and does nothing - it does not error loudly. Also: HPA scales on CPU
and memory only if you configure it, and it will never fix a memory *leak* (the pod OOMKills before
scaling helps) or an I/O-bound bottleneck; queue depth or RPS via KEDA is the right tool there. And if the
Deployment still hardcodes `replicas`, Argo and the HPA fight each other forever.

### Trap 3: "The PDB protects us during rolling updates and node failures."

A PodDisruptionBudget only applies to **voluntary** disruptions that go through the Eviction API -
`kubectl drain`, cluster upgrades, descheduler. A Deployment rollout deletes pods directly and never
consults the PDB; neither does a node going NotReady, an OOMKill, or `kubectl delete pod`. Two more
details: `minAvailable: 1` on a single-replica workload blocks drains forever (nothing can be evicted), and
a PDB whose selector matches no pods silently protects nothing. Ours are `minAvailable: 1` on
multi-replica Deployments, which is the only combination where the guarantee is meaningful.

### Trap 4: "We have NetworkPolicies, so traffic is restricted."

Only if the CNI enforces them - Calico, Cilium and Antrea do; the default kindnet in a stock kind cluster
does not, and the API server will happily accept the objects while every packet flows. Verify by testing:
`kubectl -n platform exec` from a pod and try a connection that should be denied. Also check the policy's
own correctness: `default-deny-all` with `policyTypes: [Ingress, Egress]` blocks DNS too, which is why
`allow-dns-egress` exists; a `namespaceSelector` matching `ingress-nginx` breaks the moment the controller
is installed elsewhere; and policies are additive - a second allow rule cannot re-deny what the first
allowed.

### Trap 5: "Argo CD `selfHeal` and `prune` mean the cluster always matches Git."

`selfHeal` reverts drift *on objects Argo manages*, but it does not reconcile everything: it will not
restart pods when a ConfigMap changes (env vars are snapshotted at container start), so the cluster matches
Git and the running process does not. `prune` deletes resources that were tracked and have disappeared from
Git - and it is scoped by the AppProject's allowed kinds, so a blacklisted kind is not managed at all
(`ResourceQuota`/`LimitRange` in `argocd/projects.yaml`). And `--force`/replace semantics, CRD removal and
namespace termination all have their own failure modes. The correct claim is narrower and stronger:
"Git is the only writer, and drift is corrected on the objects Argo owns - which is why production has no
automated sync block and a human reads the diff."

---

### Closing note for the candidate

If you are asked something not in this list, fall back to the three questions that always work: what does
the *controller* do when this field changes, what happens at *admission* time, and what fails *first* in
the request path. Those three cover most of Kubernetes, and this repo gives you a concrete file for each
answer.
