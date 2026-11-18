# Loki

Loki runs in the `logging` namespace together with Promtail. The manifests live in [`logging/`](../../logging/) so that a single kustomization owns both the store and the collector:

- [`logging/loki/config.yml`](../../logging/loki/config.yml) — single-binary Loki, filesystem storage, TSDB schema v13, 168 h retention, compaction.
- [`logging/loki/deployment.yaml`](../../logging/loki/deployment.yaml) — StatefulSet with a 2 Gi PVC and a `loki` Service on 3100.
- [`logging/promtail/config.yml`](../../logging/promtail/config.yml) — pod discovery, JSON parsing, `level`/`service` label extraction.
- [`logging/promtail/daemonset.yaml`](../../logging/promtail/daemonset.yaml) — DaemonSet with RBAC to list pods and read `/var/log/pods`.

Grafana is provisioned with a Loki datasource (`monitoring/grafana/provisioning/datasources/datasource.yml`).

Apply and query:

```powershell
kubectl apply -k logging
kubectl -n logging port-forward svc/loki 3100:3100
# http://localhost:3100/ready  → ready
```

```logql
{namespace="platform"} | json | level="ERROR"
{app="order-service"} |= "order_created"
```

See [`docs/MONITORING.md`](../../docs/MONITORING.md) for query patterns and troubleshooting.
