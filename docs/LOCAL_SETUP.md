# Local setup with Docker Compose

Fastest way to see the whole application. No Kubernetes required.

## Prerequisites

- Docker Desktop with the WSL2 backend, ≥ 4 GB memory allocated
- PowerShell 7 (Windows) or bash (Linux/macOS)
- Ports free: 13000, 13001, 15432, 18001-18005, 18081, 19090, 19093

## 1. Configure environment (optional)

```powershell
Copy-Item .env.example .env
# edit values; .env is git-ignored
```

Defaults are safe for local use: `POSTGRES_PASSWORD=platform`, `PUBLIC_API_KEY=demo-public-key`, `PLATFORM_API_TOKEN=platform-demo-token`, `INTERNAL_API_TOKEN=dev-internal-token`. These are **demo credentials for a local stack only**.

## 2. Start

```powershell
docker compose --profile observability up -d --build
docker compose ps
```

Ten containers start: postgres, five services, gateway, platform-api, frontend, and the observability profile (prometheus, alertmanager, grafana).

## 3. Verify

```powershell
curl http://localhost:18005/api/health
./scripts/smoke-test.ps1
```

Expected: `status: ok` with four dependencies `ok`, then a full order flow ending in `ORDER CREATED` and a stock decrement.

## 4. Use it

| What | Where |
|---|---|
| Operations dashboard | http://localhost:13000/ops |
| Storefront (real API calls) | http://localhost:13000/store |
| Gateway health | http://localhost:18005/api/health |
| Platform API health | http://localhost:18081/api/health |
| Prometheus | http://localhost:19090 |
| Grafana | http://localhost:13001 (admin/admin) |
| Alertmanager | http://localhost:19093 |

The dashboard's Settings page stores the API base URL and bearer token in `localStorage`. Defaults are `http://localhost:18081` and `platform-demo-token`.

**Demo mode**: compose runs `platform-api` with `PLATFORM_DEMO_MODE=true` because the bridge network cannot reach the Kind API server. Every response then carries `meta.source="demo"` and the UI shows a persistent amber banner. Live data requires the in-cluster deployment.

## 5. Create data through the gateway

```bash
KEY="X-API-Key: demo-public-key"
curl -s -X POST http://localhost:18005/api/users -H "$KEY" -H 'Content-Type: application/json' \
  -d '{"email":"ada@example.com","full_name":"Ada Lovelace","tier":"premium"}'

curl -s -X POST http://localhost:18005/api/products -H "$KEY" -H 'Content-Type: application/json' \
  -d '{"sku":"WIDGET-001","name":"Precision Widget","price_cents":2499,"stock":25}'
```

Then place an order with the returned ids (send `Idempotency-Key` to make retries safe).

## 6. Run the services without Docker (optional)

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-dev.txt
docker compose up -d postgres
$env:DATABASE_URL="postgresql+asyncpg://platform:platform@localhost:15432/users"
$env:INTERNAL_API_TOKEN="dev-internal-token"
Push-Location applications/user-service; ...\uvicorn app.main:app --port 8001; Pop-Location
```

Each service reads `DATABASE_URL`, `INTERNAL_API_TOKEN`, `LOG_LEVEL` and its upstream `*_SERVICE_URL` variables.

## 7. Logs and cleanup

```powershell
docker compose logs -f api-gateway
docker compose logs -f order-service | Select-String "order_created"
docker compose --profile observability down          # keep volumes
docker compose --profile observability down -v       # delete data
```

## 8. Troubleshooting quick hits

| Symptom | Fix |
|---|---|
| `port is already allocated` | Another stack owns it; change the host port in `docker-compose.yml` |
| Services restart while postgres starts | Expected; schema init retries 30 × 2 s |
| Dashboard shows DEMO DATA | Compose mode by design — use the Kind deployment for live data |
| `401 unauthorized` on writes | Send `X-API-Key: demo-public-key` |
| Grafana empty | Prometheus needs ~1 scrape interval; confirm targets at :19090/targets |
