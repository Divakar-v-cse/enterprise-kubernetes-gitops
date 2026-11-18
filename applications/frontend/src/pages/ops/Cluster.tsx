import { api } from "../../lib/api";
import type { OverviewCluster, PlatformHealth } from "../../lib/api";
import { useAsync, useResource } from "../../lib/useApi";
import { Badge } from "../../components/Badge";
import { DataTable } from "../../components/DataTable";
import type { Column } from "../../components/DataTable";
import { DemoBanner } from "../../components/DemoBanner";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { Loading } from "../../components/Loading";
import { StatCard } from "../../components/StatCard";
import {
  formatDateTime,
  formatNumber,
  formatUptime,
  percent,
  statusTone,
  text,
} from "../../lib/format";

interface ClusterRow {
  key: string;
  name: string;
  version: string;
  provider: string;
  status: string;
  namespaces: number;
  nodes: string;
}

const columns: Array<Column<ClusterRow>> = [
  { key: "name", header: "Cluster", render: (row) => <code>{row.name}</code> },
  { key: "version", header: "Kubernetes" },
  { key: "provider", header: "Provider" },
  { key: "status", header: "Status", render: (row) => <Badge tone={statusTone(row.status)}>{row.status}</Badge> },
  { key: "nodes", header: "Nodes ready", align: "right" },
  { key: "namespaces", header: "Namespaces", align: "right", render: (row) => formatNumber(row.namespaces) },
];

export function Cluster() {
  const overview = useResource<OverviewCluster>(() => api.clusterOverview(), []);
  const health = useAsync<PlatformHealth>(() => api.health());

  const data = overview.data;
  const rows: ClusterRow[] = data
    ? [
        {
          key: data.id,
          name: data.cluster.name,
          version: data.cluster.version,
          provider: data.cluster.provider,
          status: data.cluster.status,
          namespaces: data.namespaces,
          nodes: `${data.nodes.ready}/${data.nodes.total}`,
        },
      ]
    : [];

  return (
    <div className="page">
      <DemoBanner meta={overview.meta} scope="Cluster" />

      <div className="page-head">
        <div>
          <h2 className="page-title">Cluster</h2>
          <p className="page-sub">Capacity, control-plane health and API connectivity</p>
        </div>
        <button
          type="button"
          className="button button--ghost button--sm"
          onClick={() => {
            overview.reload();
            health.reload();
          }}
        >
          Refresh
        </button>
      </div>

      {overview.loading ? <Loading label="Loading cluster inventory" rows={3} /> : null}
      {overview.error ? (
        <ErrorState error={overview.error} onRetry={overview.reload} context="Could not load cluster inventory" />
      ) : null}

      {data && !overview.loading && !overview.error ? (
        <>
          <section className="stat-grid" aria-label="Cluster KPIs">
            <StatCard
              label="Control plane"
              value={data.cluster.status}
              hint={data.cluster.version}
              tone={statusTone(data.cluster.status)}
            />
            <StatCard
              label="Nodes ready"
              value={`${data.nodes.ready}/${data.nodes.total}`}
              hint={`${data.nodes.cpu_capacity_cores} CPU cores · ${data.nodes.memory_capacity_gib} GiB`}
              tone={data.nodes.ready === data.nodes.total ? "ok" : "warn"}
            />
            <StatCard
              label="CPU used"
              value={percent(data.resource_usage.cpu_percent)}
              hint={`${formatNumber(data.resource_usage.cpu_millicores)} millicores`}
              tone={data.resource_usage.cpu_percent > 80 ? "warn" : "neutral"}
            />
            <StatCard
              label="Memory used"
              value={percent(data.resource_usage.memory_percent)}
              hint={`${formatNumber(data.resource_usage.memory_mib)} MiB`}
              tone={data.resource_usage.memory_percent > 85 ? "warn" : "neutral"}
            />
          </section>

          <section className="card" aria-labelledby="cluster-table">
            <header className="card__head">
              <h3 id="cluster-table" className="card__title">Cluster inventory</h3>
              <span className="card__hint">Source: {overview.meta?.source}</span>
            </header>
            {rows.length === 0 ? (
              <EmptyState title="No clusters returned" message="/api/clusters returned an empty list." />
            ) : (
              <DataTable columns={columns} rows={rows} rowKey={(row) => row.key} caption="Cluster inventory" />
            )}
          </section>

          <div className="grid grid--two">
            <section className="card" aria-labelledby="capacity">
              <header className="card__head">
                <h3 id="capacity" className="card__title">Capacity</h3>
              </header>
              <dl className="facts">
                <div>
                  <dt>CPU capacity</dt>
                  <dd>{data.nodes.cpu_capacity_cores} cores</dd>
                </div>
                <div>
                  <dt>Memory capacity</dt>
                  <dd>{data.nodes.memory_capacity_gib} GiB</dd>
                </div>
                <div>
                  <dt>Pods scheduled</dt>
                  <dd>{formatNumber(data.pods.total)}</dd>
                </div>
                <div>
                  <dt>Deployments</dt>
                  <dd>{formatNumber(data.deployments.total)}</dd>
                </div>
                <div>
                  <dt>Cluster created</dt>
                  <dd>{formatDateTime(data.cluster.created_at)}</dd>
                </div>
                <div>
                  <dt>Snapshot</dt>
                  <dd>{formatDateTime(overview.meta?.generated_at)}</dd>
                </div>
              </dl>
            </section>

            <section className="card" aria-labelledby="api-health">
              <header className="card__head">
                <h3 id="api-health" className="card__title">Platform API health</h3>
                {health.data ? <Badge tone={statusTone(health.data.status)}>{health.data.status}</Badge> : null}
              </header>
              {health.loading ? <p className="muted">Probing /api/health…</p> : null}
              {health.error ? (
                <ErrorState error={health.error} onRetry={health.reload} context="Health probe failed" />
              ) : null}
              {health.data ? (
                <dl className="facts">
                  <div>
                    <dt>Service</dt>
                    <dd>{text(health.data.service)}</dd>
                  </div>
                  <div>
                    <dt>Version</dt>
                    <dd>{text(health.data.version)}</dd>
                  </div>
                  <div>
                    <dt>Uptime</dt>
                    <dd>{formatUptime(health.data.uptime_seconds)}</dd>
                  </div>
                  <div>
                    <dt>Auth enabled</dt>
                    <dd>{health.data.auth_enabled ? "yes" : "no"}</dd>
                  </div>
                  <div>
                    <dt>Cluster connected</dt>
                    <dd>{health.data.cluster.connected ? "yes" : "no"}</dd>
                  </div>
                  <div>
                    <dt>Data source</dt>
                    <dd>
                      <code>{health.data.cluster.data_source}</code>
                    </dd>
                  </div>
                  {health.data.cluster.error ? (
                    <div className="facts__wide">
                      <dt>Cluster error</dt>
                      <dd>{health.data.cluster.error}</dd>
                    </div>
                  ) : null}
                </dl>
              ) : null}
            </section>
          </div>
        </>
      ) : null}
    </div>
  );
}
