# GitOps Platform — Frontend

React 18 + TypeScript + Vite single-page app for the **Enterprise Kubernetes GitOps
Platform** portfolio project. It contains two clearly separated areas:

| Area | Route | Backend |
| --- | --- | --- |
| Ops dashboard (read-only control plane) | `/ops/*` | `platform-api` (FastAPI, default `http://localhost:18081`) |
| Storefront demo (microservices contract) | `/store` | `api-gateway` (FastAPI, default `http://localhost:18000`) |

No UI framework, no chart library, no axios — plain CSS, hand-written SVG charts,
`fetch` with `AbortController`.

## Run

```bash
cd applications/frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # tsc -b + vite build -> dist/
npm run preview    # serve the production build
```

Node 22 is what the project is built and verified with.

There is **no dev proxy**: the app calls absolute URLs configured at runtime, so the
platform API and gateway must allow the frontend origin via CORS (the API defaults
already allow `http://localhost:5173`, `http://localhost:3000`, `http://localhost:8080`).

## Configuration (no environment variables)

Settings live entirely in the browser (`localStorage` key `gitops-platform.settings.v1`)
and are edited on **/ops/settings**:

| Setting | Default | Transport |
| --- | --- | --- |
| Platform API base URL | `http://localhost:18081` | `Authorization: Bearer <token>` |
| Platform bearer token | `platform-demo-token` | header on every platform-api call |
| API gateway base URL | `http://localhost:18000` | storefront reads + writes |
| Gateway API key | `demo-public-key` | `X-API-Key` on `POST /api/users`, `POST /api/orders` |

Settings also provides a connection test (`GET /api/health` on either service), a
demo-mode explanation and links to the OpenAPI docs (`/api/docs`) of both services.
The page never pretends to mutate the cluster — the platform API is read-only.

Request behaviour (`src/lib/api.ts`): 8 s timeout, typed request/response interfaces,
normalised errors (`timeout | network | http | parse`). Failed requests surface an
error state with the retry button; no fixture fallback is invented in the browser.

## Page map

| Route | Page file | Data source |
| --- | --- | --- |
| `/ops` | `pages/ops/Overview.tsx` | `GET /api/clusters` (cluster + pod/deployment/GitOps rollup) |
| `/ops/cluster` | `pages/ops/Cluster.tsx` | `GET /api/clusters`, `GET /api/health` |
| `/ops/namespaces` | `pages/ops/Namespaces.tsx` | `GET /api/namespaces?limit&offset&q` |
| `/ops/workloads` | `pages/ops/Workloads.tsx` | `GET /api/workloads?namespace&kind&limit&offset` |
| `/ops/deployments` | `pages/ops/Deployments.tsx` | `GET /api/deployments?namespace&limit&offset` |
| `/ops/pods` | `pages/ops/Pods.tsx` | `GET /api/pods?namespace&phase&limit&offset` |
| `/ops/services` | `pages/ops/Services.tsx` | `GET /api/services?namespace&limit&offset` |
| `/ops/gitops` | `pages/ops/GitOps.tsx` | `GET /api/gitops/status` |
| `/ops/monitoring` | `pages/ops/Monitoring.tsx` | `GET /api/metrics` (4 SVG series + top pods) |
| `/ops/logs` | `pages/ops/Logs.tsx` | `GET /api/logs?namespace&pod&level&limit` |
| `/ops/alerts` | `pages/ops/Alerts.tsx` | `GET /api/alerts?severity&status` |
| `/ops/security` | `pages/ops/Security.tsx` | `GET /api/security/findings?severity&limit&offset` |
| `/ops/history` | `pages/ops/History.tsx` | `GET /api/gitops/status` + `GET /api/deployments` (derived timeline) |
| `/ops/settings` | `pages/ops/Settings.tsx` | `GET /api/health` (connection test only) |
| `/store` | `pages/Storefront.tsx` | `GET /api/health`, `GET /api/catalog/overview`, `GET/POST /api/orders`, `POST /api/users` |
| `*` | `pages/NotFound.tsx` | — |

Every ops data page renders: hero KPI row → real table/list → skeleton while loading →
error state on failure → empty state when the API returns no rows.

## Demo-data honesty

`platform-api` returns `meta.source` on every payload. When `meta.source !== "cluster"`
(source `demo` or `security-scan`) the `DemoBanner` component shows a persistent
amber **DEMO DATA** strip, including `meta.reason` when present (e.g.
`PLATFORM_DEMO_MODE=true` or a cluster connectivity error). Demo data is never labelled
live and never generated in the frontend.

**Deployment history** (`/ops/history`) is derived, not stored: one timeline entry per
Argo CD application using `last_synced_at`, `revision`, sync/health status and the
matching Deployment's replica readiness, sorted newest-first. The page states
"Derived from Argo CD application status" and lists applications that returned no
sync timestamp separately — no synthetic events are added.

## Structure

```
src/
  main.tsx              React root + SettingsProvider + BrowserRouter
  App.tsx               routes (14 ops pages, storefront, 404)
  styles.css            dark "control plane" theme, CSS variables, responsive
  lib/
    api.ts              typed client, endpoint wrappers, error normalisation, timeout
    format.ts           dates, relative time, percentages, money, status→tone
    settings.tsx        persisted runtime config (localStorage)
    useApi.ts           useResource (envelope) / useAsync loaders
  components/
    Layout.tsx          sidebar + topbar shell, skip link, page titles
    Sidebar.tsx         5 nav groups / 14 routes + storefront entry
    Topbar.tsx          title, endpoint pill, docs + storefront links
    StatCard.tsx        KPI tile
    Badge.tsx           semantic status pill
    DataTable.tsx       generic typed table (headers, optional expandable rows)
    LineChart.tsx       hand-written SVG line/area chart
    EmptyState.tsx      empty state
    ErrorState.tsx      normalised error state with retry
    Loading.tsx         skeleton
    DemoBanner.tsx      DEMO DATA banner
    Pagination.tsx      offset pagination from meta
  pages/
    ops/*.tsx           14 ops pages
    Storefront.tsx      product grid, create user, create order, order list, gateway health
    NotFound.tsx        404
```

## Notes

- Accessibility: `aside`/`nav`/`main` landmarks, skip link, visible focus rings,
  labelled buttons and form fields, `scope="col"` table headers, `aria-expanded`
  on expandable pods, live regions for banners and async results.
- No image assets; bundle is ~264 kB JS / ~24 kB CSS before gzip.
- The storefront generates an `Idempotency-Key` with `crypto.randomUUID()` and rotates
  it after each successful submission; re-submitting with the same key returns the
  existing order rather than duplicating it.
