# Recording checklist

## Tooling

- OBS Studio (free) or Windows Xbox Game Bar (`Win+G`) for full-screen capture.
- 1920×1080, 30 fps, MP4. Target ≈ 5 minutes, under 100 MB for GitHub.
- Microphone check: 10-second test recording, listen back before the real take.

## Environment readiness

```powershell
docker compose --profile observability up -d
kubectl get nodes
kubectl -n platform get pods
kubectl -n argocd get applications
```

- [ ] All platform pods `Running` and `READY`
- [ ] Argo CD applications `Synced` (except `platform-production`, which is intentionally `OutOfSync`)
- [ ] Dashboard loads at http://localhost:13000/ops with the right data-source badge
- [ ] Grafana opens with the Application Performance dashboard populated
- [ ] Prometheus `/targets` shows platform pods `UP`
- [ ] Storefront order completes (pre-create a user and a product to save time)
- [ ] Terminal font ≥ 16 pt, dark theme, prompt shortened (`function prompt { "PS> " }`)

## Browser tabs, in order

1. `http://localhost:13000/ops` — dashboard overview
2. `http://localhost:13000/store` — storefront
3. Grafana → Application Performance
4. Prometheus → `/targets`
5. Grafana → Explore → Loki
6. Argo CD UI (`kubectl -n argocd port-forward svc/argocd-server 8080:443`)
7. GitHub → Actions (only if a workflow has actually run)

## Segment checklist

- [ ] 0:00 Problem statement over `docs/architecture.png`
- [ ] 0:30 Create user → create order → stock decreases
- [ ] 1:15 `kubectl get deploy,pods,hpa,pdb` and one security-context grep
- [ ] 2:00 Argo CD: 13 applications, sync waves, production `OutOfSync`
- [ ] 2:30 Drift demo: scale to 3, show `OutOfSync`, self-heal back
- [ ] 2:45 Grafana golden signals + Prometheus targets
- [ ] 3:15 Loki query filtered to `level="ERROR"`
- [ ] 3:30 HPA behaviour (or state the single-node limitation on camera)
- [ ] 4:00 Rollback via `git revert` + Argo CD
- [ ] 4:15 NetworkPolicy + `kubectl auth can-i get secrets`
- [ ] 4:45 CI workflow file tour and closing statement

## Before publishing

- [ ] No tokens, kubeconfig paths, personal email or internal hostnames on screen
- [ ] Blur the Argo CD admin password and any terminal history containing secrets
- [ ] Trim dead time (waiting for pods, loading spinners)
- [ ] Upload `demo/demo.mp4` or link an unlisted video in the README
- [ ] Keep `demo/DEMO_SCRIPT.md` in sync with what was actually recorded

## If a component is unavailable

Say it plainly, show the configuration, and move on. Do not record demo-mode data as if it were live — the dashboard's amber banner makes that obvious and it undermines the whole project if it appears deliberate.
