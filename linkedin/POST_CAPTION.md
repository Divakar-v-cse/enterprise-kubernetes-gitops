Anyone can deploy to Kubernetes. The hard part is proving that what is running matches what is in Git.

I built **Enterprise Kubernetes GitOps Platform** — microservices delivery with argo cd, real metrics and default-deny networking.

**The problem**
- Manual kubectl deployments drift from Git within days.
- Scaling and rollback are guesswork without metrics or a defined process.
- Default-flat cluster networking exposes every service to every other service.

**What I built**
- Five FastAPI services plus a React operations dashboard on a local Kind cluster.
- Argo CD app-of-apps: automated sync in development, manual approval for production.
- Prometheus, Grafana, Alertmanager and Loki deployed in-cluster, not mocked.
- Default-deny network policies, read-only RBAC for the dashboard, PDBs and quotas.

**Stack**
- **Runtime:** Kubernetes 1.34 (Kind), Docker, Helm 4, Kustomize
- **Delivery:** Argo CD 2.13, GitHub Actions, Git as desired state
- **Observability:** Prometheus, Grafana, Alertmanager, Loki + Promtail
- **Application:** FastAPI, React + TypeScript, PostgreSQL
- **Security:** Trivy, Checkov, Bandit, RBAC, NetworkPolicy

**Engineering guard rails**
- Startup, readiness and liveness probes on every workload.
- HPA on CPU, PodDisruptionBudgets, rolling updates with maxUnavailable 0.
- Default-deny ingress and egress; explicit allow-list between services only.
- Dashboard uses a read-only ServiceAccount — no cluster-admin anywhere.
- Fixed 3 CRITICAL CVEs by moving the nginx base to 1.29-alpine; rescan clean.

**What is verified**
- 46 service tests and 47 manifest/Helm policy tests pass.
- CI and Security pipelines green on main; 7 images built per run.
- Argo CD reports every application Synced and Healthy on the local cluster.

**The part I underestimated**
GitOps is only trustworthy when drift is visible. Turning on self-heal surfaced a kustomize path-scope error that manual deploys had been hiding.

Swipe through the carousel for the architecture, the delivery workflow and the exact components in use.

Repository: https://github.com/Divakar-v-cse/enterprise-kubernetes-gitops

If you work on platform or cloud teams, I would like your critique more than your compliment — especially on where this design would break at 10× scale.

#DevOps #CloudEngineering #AWS #Kubernetes #Terraform #PlatformEngineering #SRE #GitOps #CICD #Observability
