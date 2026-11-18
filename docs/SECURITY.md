# Security architecture

## Principles

1. **Least privilege everywhere** — workloads get no Kubernetes API access unless they need it; the dashboard gets read-only verbs and cannot read Secrets.
2. **Deny by default** — network traffic is denied in both directions until a policy allows it.
3. **No secrets in Git** — examples contain `REPLACE_ME`; real values are generated at deploy time.
4. **Immutable, non-root images** — pinned tags, UID 10001, read-only root filesystem, dropped capabilities.
5. **Evidence, not claims** — every control below is either enforced by a test or observable with a command.

## Workload hardening

| Control | Implementation |
|---|---|
| Non-root | `runAsNonRoot: true`, UID/GID 10001 (101 for NGINX, 65534 for exporters) |
| No privilege escalation | `allowPrivilegeEscalation: false` |
| Capabilities | `drop: ["ALL"]` |
| Seccomp | `seccompProfile.type: RuntimeDefault` |
| Filesystem | `readOnlyRootFilesystem: true`, `emptyDir` at `/tmp` (and `/var/cache/nginx` for the frontend) |
| Service account tokens | `automountServiceAccountToken: false` on all app pods; only platform-api mounts one |
| Pod Security Standards | `restricted` enforced on `platform` and `platform-prod` namespaces |

## RBAC

```
platform-api  → ClusterRole platform-api-readonly
                  get,list on nodes/namespaces/pods/services/events/pvcs/configmaps,
                  apps deployments/statefulsets/daemonsets/replicasets,
                  batch jobs/cronjobs, networking ingresses/networkpolicies,
                  autoscaling HPAs, metrics.k8s.io, argoproj.io applications
                  NO secrets, NO write verbs, NO exec
ci-deployer   → Role platform-deployer (get/list/watch + patch deployments)
developers    → Role platform-developer (read-only, plus pods/log and portforward)
```

Verify:

```powershell
kubectl auth can-i get secrets --as=system.serviceaccount:platform:platform-api -n platform   # no
kubectl auth can-i list pods   --as=system.serviceaccount:platform:platform-api -n platform   # yes
```

`tests/test_manifests.py::test_platform_api_rbac_is_read_only` fails the build if a write verb or `secrets` appears in that role.

## Network policies

`kubernetes/policies/network-policies.yaml` starts with `default-deny-all` (Ingress **and** Egress) and adds only:

- ingress-controller → frontend, gateway, platform-api
- gateway → user/product/order/notification
- order-service → user/product/notification/postgres
- user/product/notification → postgres
- monitoring → metrics ports (8000-8004, 8080)
- DNS egress to kube-system:53
- platform-api egress to the API server, Prometheus, Alertmanager, Loki

A new dependency without a matching policy fails closed — connect timeouts, not silent access.

## Secrets

- `.env`, `*.pem`, `kubeconfig`, `**/secrets.yaml` are git-ignored, and `tests/test_repository_hygiene.py` fails if they appear.
- `kubernetes/core/secret.example.yaml` and `kubernetes/base/secret.example.yaml` contain only placeholders.
- Real values: `scripts/create-dev-secrets.ps1` generates random material with `RandomNumberGenerator` and applies it via `kubectl create secret` — never written to disk.
- Production guidance: External Secrets Operator, Sealed Secrets, or SOPS with age/KMS; rotate `POSTGRES_PASSWORD` and `INTERNAL_API_TOKEN` together.

```powershell
kubectl -n platform get secret platform-secrets -o jsonpath='{.data}'   # ciphertext only, base64
```

## Supply chain

| Layer | Tool | Where |
|---|---|---|
| Container CVEs | Trivy (image matrix) | `security.yml`, `Jenkinsfile` |
| Misconfiguration | Trivy config, Checkov (k8s + Helm) | `security.yml`, `scripts/security-scan.ps1` |
| Python static analysis | Bandit | `scripts/security-scan.ps1` |
| Dependency advisories | pip-audit, Dependabot | `security.yml`, `.github/dependabot.yml` |
| Committed secrets | gitleaks + tracked-file guard | `security.yml` |
| Manifest policy | 47 pytest assertions | `tests/test_manifests.py` |

## Scan results

Full detail: [`security/SECURITY_REPORT.md`](../security/SECURITY_REPORT.md).

- **Bandit:** 14 findings, all LOW (deliberate exception handling), 0 medium/high.
- **Checkov (Kubernetes):** 728 passed, 29 failed — accepted patterns (secrets via `secretKeyRef`), one pending fix (postgres SA token), and Helm placeholder false positives.
- **pip-audit:** 16 advisories in `pytest` and `urllib3`, both **dev-only** dependencies; no runtime package affected.
- **Trivy / Kubescape:** not executed locally in this environment; configured in CI. Limitation documented rather than claimed as passing.

## Threat notes

| Threat | Mitigation |
|---|---|
| Compromised frontend pod | No service account, no egress policy, static content only |
| Lateral movement from a service | Default-deny egress; each service reaches only its declared dependencies |
| Dashboard credential theft | Read-only token; cannot read Secrets or mutate workloads |
| Leaked repo | No credentials committed; deploy-time generation; gitleaks in CI |
| Oversell / abuse via API | API key on writes, 240 req/min per client, idempotency keys, atomic stock decrement |
| Container escape | Non-root, dropped caps, seccomp, read-only FS, no hostPath except node-exporter |

## Residual risks

- Local `platform-secrets` are long-lived (no rotation controller).
- Alertmanager has no external receiver, so alert delivery is UI-only.
- No TLS on the local ingress (HTTP 18080); production overlay enables `ssl-redirect` and expects cert-manager.
- Single-node cluster means no true multi-AZ failure domain.
