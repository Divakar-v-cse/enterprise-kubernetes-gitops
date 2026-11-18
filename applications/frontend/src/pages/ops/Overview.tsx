import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import type { OverviewCluster } from "../../lib/api";
import { useResource } from "../../lib/useApi";
import { DemoBanner } from "../../components/DemoBanner";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { Loading } from "../../components/Loading";
import { StatCard } from "../../components/StatCard";
import { Badge } from "../../components/Badge";
import { DataTable } from "../../components/DataTable";
import type { Column } from "../../components/DataTable";
import {
  formatDateTime,
  formatNumber,
  percent,
  statusTone,
  text,
} from "../../lib/format";

interface NamespaceShare {
  name: string;
  pods: number;
  share: number;
}

const namespaceColumns: Array<Column<NamespaceShare>> = [
  { key: "name", header: "Namespace", render: (row) => <code>{row.name}</code> },
  { key: "pods", header: "Pods", align: "right", render: (row) => formatNumber(row.pods) },
  {
    key: "share",
    header: "Share of pods",
    align: "right",
    render: (row) => (
      <div className="bar-cell">
        <span className="meter meter--inline">
          <span className="meter__fill" style={{ width: `${Math.min(row.share, 100)}%` }} />
        </span>
        <span>{percent(row.share)}</span>
      </div>
    ),
  },
];

export function Overview() {
  const { data, meta, loading, error, reload } = useResource<OverviewCluster>(
    () => api.clusterOverview(),
    [],
  );

  const totalPods = data?.pods.total ?? 0;
  const namespaceRows: NamespaceShare[] = data
    ? Object.entries(data.pods_by_namespace ?? {})
        .map(([name, pods]) => ({ name, pods, share: totalPods ? (pods / totalPods) * 100 : 0 }))
        .sort((a, b) => b.pods - a.pods)
    : [];

  return (
    <div className="page">
      <DemoBanner meta={meta} scope="Platform overview" />

      <div className="page-head">
        <div>
          <h2 className="page-title">Platform Overview</h2>
          <p className="page-sub">
            {meta?.generated_at ? `Snapshot generated ${formatDateTime(meta.generated_at)}` : "Awaiting snapshot"}
            {meta?.cluster ? ` · cluster ${meta.cluster}` : ""}
          </p>
        </div>
        <button type="button" className="button button--ghost button--sm" onClick={reload}>
          Refresh
        </button>
      </div>

      {loading ? <Loading label="Loading platform overview" rows={5} /> : null}
      {error ? <ErrorState error={error} onRetry={reload} context="Could not load platform overview" /> : null}

      {data && !loading && !error ? (
        <>
          <section className="stat-grid" aria-label="Platform KPIs">
            <StatCard
              label="Nodes ready"
              value={`${data.nodes.ready}/${data.nodes.total}`}
              hint={`${data.nodes.cpu_capacity_cores} cores · ${data.nodes.memory_capacity_gib} GiB capacity`}
              tone={data.nodes.ready === data.nodes.total ? "ok" : "warn"}
            />
            <StatCard
              label="Pods running"
              value={formatNumber(data.pods.running)}
              hint={`${formatNumber(data.pods.pending)} pending · ${formatNumber(data.pods.failed)} failed of ${formatNumber(data.pods.total)}`}
              tone={data.pods.failed > 0 ? "warn" : "ok"}
            />
            <StatCard
              label="Deployments available"
              value={`${data.deployments.available}/${data.deployments.total}`}
              hint={`${data.deployments.unavailable} unavailable`}
              tone={data.deployments.unavailable > 0 ? "warn" : "ok"}
            />
            <StatCard
              label="GitOps synced"
              value={`${data.gitops.synced}/${data.gitops.applications}`}
              hint={`${data.gitops.out_of_sync} out of sync · ${data.gitops.degraded} degraded`}
              tone={data.gitops.out_of_sync === 0 && data.gitops.degraded === 0 ? "ok" : "warn"}
              footer={
                <Link className="link" to="/ops/gitops">
                  Inspect applications
                </Link>
              }
            />
            <StatCard
              label="Firing alerts"
              value={formatNumber(data.alerts.firing)}
              hint={`${data.alerts.critical} critical`}
              tone={data.alerts.critical > 0 ? "error" : data.alerts.firing > 0 ? "warn" : "ok"}
              footer={
                <Link className="link" to="/ops/alerts">
                  Open alerts
                </Link>
              }
            />
            <StatCard
              label="Request throughput"
              value={`${data.throughput_rps} rps`}
              hint={`Error rate ${percent(data.error_rate_percent)}`}
              tone={data.error_rate_percent > 2 ? "warn" : "neutral"}
            />
          </section>

          <div className="grid grid--two">
            <section className="card" aria-labelledby="cluster-facts">
              <header className="card__head">
                <h3 id="cluster-facts" className="card__title">Cluster</h3>
                <Badge tone={statusTone(data.cluster.status)}>{data.cluster.status}</Badge>
              </header>
              <dl className="facts">
                <div>
                  <dt>Name</dt>
                  <dd>{text(data.cluster.name)}</dd>
                </div>
                <div>
                  <dt>Kubernetes</dt>
                  <dd>{text(data.cluster.version)}</dd>
                </div>
                <div>
                  <dt>Provider</dt>
                  <dd>{text(data.cluster.provider)}</dd>
                </div>
                <div>
                  <dt>Namespaces</dt>
                  <dd>{formatNumber(data.namespaces)}</dd>
                </div>
                <div>
                  <dt>Created</dt>
                  <dd>{formatDateTime(data.cluster.created_at)}</dd>
                </div>
                <div>
                  <dt>Data source</dt>
                  <dd>
                    <code>meta.source={meta?.source}</code>
                  </dd>
                </div>
              </dl>
            </section>

            <section className="card" aria-labelledby="resource-usage">
              <header className="card__head">
                <h3 id="resource-usage" className="card__title">Resource usage</h3>
                <span className="card__hint">{formatNumber(data.nodes.total)} node(s)</span>
              </header>
              <div className="meter-row">
                <div className="meter-row__label">
                  <span>CPU</span>
                  <span>
                    {formatNumber(data.resource_usage.cpu_millicores)}m · {percent(data.resource_usage.cpu_percent)}
                  </span>
                </div>
                <span className="meter">
                  <span
                    className={`meter__fill${data.resource_usage.cpu_percent > 80 ? " meter__fill--warn" : ""}`}
                    style={{ width: `${Math.min(data.resource_usage.cpu_percent, 100)}%` }}
                  />
                </span>
              </div>
              <div className="meter-row">
                <div className="meter-row__label">
                  <span>Memory</span>
                  <span>
                    {formatNumber(data.resource_usage.memory_mib)} MiB · {percent(data.resource_usage.memory_percent)}
                  </span>
                </div>
                <span className="meter">
                  <span
                    className={`meter__fill${data.resource_usage.memory_percent > 85 ? " meter__fill--warn" : ""}`}
                    style={{ width: `${Math.min(data.resource_usage.memory_percent, 100)}%` }}
                  />
                </span>
              </div>
              <ul className="kv-list">
                <li>
                  <span>Pending pods</span>
                  <strong>{formatNumber(data.pods.pending)}</strong>
                </li>
                <li>
                  <span>Failed pods</span>
                  <strong>{formatNumber(data.pods.failed)}</strong>
                </li>
                <li>
                  <span>Succeeded pods</span>
                  <strong>{formatNumber(data.pods.succeeded)}</strong>
                </li>
              </ul>
            </section>
          </div>

          <section className="card" aria-labelledby="pods-by-namespace">
            <header className="card__head">
              <h3 id="pods-by-namespace" className="card__title">Pods by namespace</h3>
              <span className="card__hint">{namespaceRows.length} namespaces reported</span>
            </header>
            {namespaceRows.length === 0 ? (
              <EmptyState
                title="No namespace distribution reported"
                message="The platform API returned an empty pods_by_namespace map."
              />
            ) : (
              <DataTable
                columns={namespaceColumns}
                rows={namespaceRows}
                rowKey={(row) => row.name}
                caption="Pod distribution by namespace"
                dense
              />
            )}
          </section>

          <section className="card" aria-labelledby="workload-glimpse">
            <header className="card__head">
              <h3 id="workload-glimpse" className="card__title">Jump into workloads</h3>
            </header>
            <div className="link-grid">
              <Link className="tile-link" to="/ops/pods">
                <span aria-hidden="true">◍</span>
                <strong>Pods</strong>
                <small>{formatNumber(data.pods.total)} total · restart counts</small>
              </Link>
              <Link className="tile-link" to="/ops/deployments">
                <span aria-hidden="true">⇪</span>
                <strong>Deployments</strong>
                <small>{data.deployments.available} ready of {data.deployments.total}</small>
              </Link>
              <Link className="tile-link" to="/ops/monitoring">
                <span aria-hidden="true">◔</span>
                <strong>Monitoring</strong>
                <small>CPU / memory / latency series</small>
              </Link>
              <Link className="tile-link" to="/ops/history">
                <span aria-hidden="true">⟲</span>
                <strong>Deployment history</strong>
                <small>Derived from Argo CD status</small>
              </Link>
            </div>
          </section>
        </>
      ) : null}

      {!loading && !error && !data ? (
        <EmptyState title="No overview payload" message="The platform API returned no cluster data." />
      ) : null}
    </div>
  );
}
