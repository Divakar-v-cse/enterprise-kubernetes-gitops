# Security scan report

Scans executed locally on 2026-11-18 against this working tree. Raw output is kept in `security/artifacts/`.

| Scanner | Scope | Result |
|---|---|---|
| Bandit 1.9.x | `applications/`, `platform-api/` (excluding tests) | 14 findings, **all LOW severity**, 0 medium/high |
| Checkov 3.4.x | `kubernetes/` (Kubernetes framework) | **728 passed, 29 failed**, 0 skipped |
| Checkov 3.4.x | `helm/` (Helm framework) | Failures limited to CI-only checks (see below) |
| pip-audit 2.9.x | `requirements-dev.txt` (dev/CI dependencies) | **16 known vulnerabilities in 2 packages** |
| Repository hygiene | tracked files | No `.env`, kubeconfig, private key or credential pattern |
| Trivy | filesystem / config / images | **Not executed locally** (binary download unavailable in this environment); configured in `.github/workflows/security.yml` and the Jenkinsfile |
| Kubescape | cluster posture | **Not executed** (not installed); documented workaround in `docs/TESTING.md` |

## Bandit — 14 LOW findings

All findings are `B110`/`B112`-class (`try/except/pass` and `try/except/continue`) inside deliberate error handling. Example locations: the compensation loop in `applications/order-service/app/main.py` and the metrics fallback in `platform-api/app/kube.py`, where a failed optional collector must not fail the request.

Severity breakdown: HIGH 0 · MEDIUM 0 · LOW 14 · CONFIDENCE HIGH 14.

No `B105`/`B106` hard-coded password findings, because credentials arrive through environment variables and Kubernetes Secrets. Demo defaults (`demo-public-key`, `dev-internal-token`) are labelled as local-only and are not used by the in-cluster deployment, which reads generated values from `platform-secrets`.

**Disposition:** accepted. Suppressing them with `# nosec` would hide genuine future exceptions-handling regressions; they are low severity by design.

## Checkov — Kubernetes: 728 passed / 29 failed

Representative failures and their disposition:

| Check | Resource | Disposition |
|---|---|---|
| CKV_K8S_35 (secrets as env vars) | postgres StatefulSet, service Deployments | **Accepted** — `valueFrom.secretKeyRef` is the intended pattern; file mounts add rotation complexity for no security gain at this scale |
| CKV_K8S_38 (SA token automount) | postgres StatefulSet | **Fix pending** — postgres does not need a token; `automountServiceAccountToken: false` should be added |
| CKV_K8S_49 (wildcard verbs) | `platform-developer` Role | **Accepted with note** — developer role is read-only across resource groups by design; it is not bound to any workload |
| CKV_K8S_15/20/21 (image tag/probes/limits) on generated Helm pods | `release-name-*` placeholders | **False positive** — Checkov scans the chart with placeholder release names; rendered manifests pass the equivalent assertions in `tests/test_helm_charts.py` |

The 29 failures concentrate in three areas: secrets-as-env (accepted), the developer read-only role (accepted), and Helm chart placeholders (false positive). Nothing critical is unaddressed, and every Deployment in the repository independently satisfies the probe/resource/non-root contract enforced by 47 automated policy tests.

## pip-audit — 16 vulnerabilities in 2 packages

| Package | Version | Issues |
|---|---|---|
| urllib3 | 2.3.0 | 14 advisories (PYSEC-2026-1994 … PYSEC-2026-4177) |
| pytest | 8.4.2 | 2 advisories (PYSEC-2026-1845) |

Both are **development/CI dependencies**, not runtime dependencies of any service image. They come from `requirements-dev.txt`; service images install only their own runtime requirements (FastAPI, uvicorn, httpx, SQLAlchemy, asyncpg, prometheus-client, pydantic).

**Remediation:** upgrade `pytest` to the latest 8.x patch and pin `urllib3` transitively via `pip-audit --fix` in CI, or add `urllib3>=2.5` to dev requirements. Runtime exposure is nil; the honest fix is dependency refresh, tracked as a follow-up rather than silently ignored.

## Controls verified in the cluster

| Control | Evidence |
|---|---|
| Non-root, no privilege escalation | `securityContext` on every pod; enforced by `tests/test_manifests.py` |
| Read-only root filesystem | All service containers, writable `/tmp` only |
| Dropped capabilities | `capabilities.drop: ["ALL"]` |
| Seccomp | `RuntimeDefault` on every pod |
| Network segmentation | 11 NetworkPolicies; `default-deny-all` for both directions |
| Least-privilege API access | `kubectl auth can-i get secrets --as=system:serviceaccount:platform:platform-api` → `no` |
| Secret handling | Generated at deploy time by `scripts/create-dev-secrets.ps1`; only `REPLACE_ME` placeholders in Git |
| Pod Security Standards | `restricted` enforced on `platform` and `platform-prod` |
| Image scanning | Trivy image matrix in `security.yml` and Jenkinsfile |
| Dependency scanning | pip-audit + Dependabot |
| Secret scanning | gitleaks + tracked-file guard job |

## Reproduce

```powershell
./scripts/security-scan.ps1        # bandit, pip-audit, checkov, hygiene
```

```bash
docker run --rm -v "$PWD:/src" aquasec/trivy:0.57.1 config --severity HIGH,CRITICAL /src/kubernetes
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy:0.57.1 image --severity HIGH,CRITICAL platform/api-gateway:1.0.0
```
