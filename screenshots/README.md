# Screenshots

All images were captured from this environment against the running local stack (Kind cluster `gitops-platform`, Kubernetes v1.34.0, plus Grafana/Prometheus port-forwards). No mockups, composites or invented UI were used.

| File | What it shows | Source |
|---|---|---|
| `01-dashboard-overview.png` | Platform Overview with live cluster counters, `meta.source=cluster`, 34 running pods, 21/21 deployments available | React dashboard → `/ops` |
| `02-pods.png` | Pod inventory with readiness, restart counts and filters | `/ops/pods` |
| `03-gitops-status.png` | Argo CD application sync/health per service | `/ops/gitops` |
| `04-monitoring.png` | CPU/memory/throughput/latency charts from `/api/metrics` | `/ops/monitoring` |
| `05-security.png` | Security findings sourced from `security/findings.json` (Bandit + Checkov) | `/ops/security` |
| `06-deployments.png` | Deployment replicas and rollout state | `/ops/deployments` |
| `07-storefront.png` | Storefront calling the live gateway API | `/store` |
| `08-grafana-dashboard.png` | Provisioned Grafana dashboard backed by Prometheus | Grafana :3000 |
| `09-prometheus-targets.png` | Scrape targets with health status | Prometheus :9090/targets |
| `10-kubectl-workloads.png` | `kubectl -n platform get pods -o wide` output | live cluster |
| `11-argocd-applications.png` | `kubectl -n argocd get applications` output | live cluster |
| `12-network-policies.png` | `kubectl -n platform get networkpolicy` output | live cluster |
| `13-security-scan.png` | Bandit, Checkov and pip-audit output summary | local scan run |

## Notes on what is *not* here

- **No GitHub Actions screenshot.** The workflows have not executed on GitHub yet, so there is no run to capture. Capturing the YAML instead would misrepresent configuration as evidence of execution.
- **No demo video.** Recording requires a screen recorder and a narrated take; `demo/DEMO_SCRIPT.md` and `demo/RECORDING_CHECKLIST.md` provide the exact sequence.
- Terminal captures (`10`-`13`) render the literal command output into a dark terminal-style image for readability; the text is the unedited output saved in `security/artifacts/`.

## Regenerating

```powershell
$env:NODE_PATH = Join-Path (npm root -g) "@mermaid-js\mermaid-cli\node_modules"
$env:GRAFANA_URL = "http://localhost:3000"
$env:PROMETHEUS_URL = "http://localhost:9090/targets"
node tools/capture-screenshots.js "http://localhost:18080/platform" "<platform-api-token>"
```

The token is the `PLATFORM_API_TOKEN` value in the `platform-secrets` Secret — never commit it.
