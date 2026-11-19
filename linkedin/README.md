# LinkedIn kit — Enterprise Kubernetes GitOps Platform

Publication assets for this project only. Everything here is generated from the
repository's own verified results; no metric is invented.

| File | Use |
|---|---|
| [`carousel.pdf`](carousel.pdf) | 8-page 16:9 carousel, upload as a LinkedIn **document post** |
| [`cover.png`](cover.png) | Cover slide, also usable as the post image |
| [`slide-problem.png`](slide-problem.png) | Problem statement slide |
| [`slide-architecture.png`](slide-architecture.png) | Architecture slide (vector source: [`../docs/architecture.mmd`](../docs/architecture.mmd)) |
| [`slide-tech-stack.png`](slide-tech-stack.png) | Technology stack slide |
| [`slide-workflow.png`](slide-workflow.png) | Delivery workflow slide |
| [`POST_CAPTION.md`](POST_CAPTION.md) | Full post copy with hook, body, repo link and hashtags |

## How to publish

1. LinkedIn → **Start a post** → **Add a document** → select `carousel.pdf`.
2. Title: `Enterprise Kubernetes GitOps Platform` (LinkedIn renders the cover automatically).
3. Paste the body from `POST_CAPTION.md`, keep the repository link, add the hashtags last.
4. Post between Tuesday and Thursday morning in your audience's timezone; reply to comments within the first hour.

## Verify a claim before posting

Every number in the carousel is reproducible from this repository:

```bash
pytest applications/api-gateway -q                       # 8 tests
pytest tests/test_manifests.py tests/test_helm_charts.py # 47 manifest/chart checks
helm lint helm/charts/api-gateway
kubectl -n argocd get applications                       # Synced / Healthy
```

If a claim cannot be reproduced on your machine, remove it from the post rather
than softening the wording.
