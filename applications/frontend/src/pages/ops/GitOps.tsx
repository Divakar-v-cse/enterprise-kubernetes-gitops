import { api } from "../../lib/api";
import type { GitOpsApplication } from "../../lib/api";
import { useResource } from "../../lib/useApi";
import { Badge } from "../../components/Badge";
import { DataTable } from "../../components/DataTable";
import type { Column } from "../../components/DataTable";
import { DemoBanner } from "../../components/DemoBanner";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { Loading } from "../../components/Loading";
import { StatCard } from "../../components/StatCard";
import { formatDateTime, formatNumber, relativeTime, statusTone, text } from "../../lib/format";

const columns: Array<Column<GitOpsApplication>> = [
  {
    key: "name",
    header: "Application",
    render: (row) => (
      <span className="pod-name">
        <strong>{row.name}</strong>
        <small>{text(row.project)}</small>
      </span>
    ),
  },
  {
    key: "sync_status",
    header: "Sync",
    render: (row) => <Badge tone={statusTone(row.sync_status)}>{row.sync_status}</Badge>,
  },
  {
    key: "health_status",
    header: "Health",
    render: (row) => <Badge tone={statusTone(row.health_status)}>{row.health_status}</Badge>,
  },
  {
    key: "revision",
    header: "Revision",
    render: (row) => (
      <span className="mono-sm">
        {text(row.revision)}
        {row.target_revision && row.target_revision !== row.revision ? ` → ${row.target_revision}` : ""}
      </span>
    ),
  },
  { key: "path", header: "Path", render: (row) => <span className="mono-sm">{text(row.path)}</span> },
  {
    key: "destination",
    header: "Destination",
    render: (row) => (
      <span className="mono-sm">
        {text(row.destination_namespace)}
        <br />
        <small className="muted">{text(row.destination)}</small>
      </span>
    ),
  },
  {
    key: "last_synced_at",
    header: "Last synced",
    render: (row) => (
      <span title={formatDateTime(row.last_synced_at)}>
        {row.last_synced_at ? relativeTime(row.last_synced_at) : "never"}
        <br />
        <small className="muted">{formatDateTime(row.last_synced_at)}</small>
      </span>
    ),
  },
  {
    key: "auto_sync",
    header: "Auto-sync",
    render: (row) => (
      <Badge tone={row.auto_sync ? "ok" : "warn"}>{row.auto_sync ? "enabled" : "manual"}</Badge>
    ),
  },
  {
    key: "message",
    header: "Message",
    render: (row) => <span className="truncate-cell">{text(row.message)}</span>,
  },
];

export function GitOps() {
  const { data, meta, loading, error, reload } = useResource<GitOpsApplication[]>(
    () => api.gitops(),
    [],
  );

  const rows = data ?? [];
  const synced = rows.filter((row) => row.sync_status === "Synced").length;
  const outOfSync = rows.filter((row) => row.sync_status !== "Synced").length;
  const degraded = rows.filter((row) => row.health_status !== "Healthy").length;
  const autoSync = rows.filter((row) => row.auto_sync).length;

  return (
    <div className="page">
      <DemoBanner meta={meta} scope="GitOps" />

      <div className="page-head">
        <div>
          <h2 className="page-title">GitOps</h2>
          <p className="page-sub">Argo CD application sync, health and revision state from /api/gitops/status</p>
        </div>
        <button type="button" className="button button--ghost button--sm" onClick={reload}>Refresh</button>
      </div>

      <section className="stat-grid" aria-label="GitOps KPIs">
        <StatCard label="Applications" value={formatNumber(rows.length)} hint={meta?.cluster ? `cluster ${meta.cluster}` : undefined} />
        <StatCard label="Synced" value={formatNumber(meta?.synced ?? synced)} tone={outOfSync === 0 ? "ok" : "neutral"} />
        <StatCard label="Out of sync" value={formatNumber(meta?.out_of_sync ?? outOfSync)} tone={outOfSync > 0 ? "warn" : "ok"} />
        <StatCard
          label="Degraded health"
          value={formatNumber(meta?.degraded ?? degraded)}
          tone={degraded > 0 ? "error" : "ok"}
          hint={`${autoSync}/${rows.length} auto-sync enabled`}
        />
      </section>

      <section className="card" aria-labelledby="gitops-table">
        <header className="card__head">
          <h3 id="gitops-table" className="card__title">Applications</h3>
          <span className="card__hint">Revisions and paths exactly as reported by Argo CD</span>
        </header>

        {loading ? <Loading label="Loading GitOps applications" /> : null}
        {error ? <ErrorState error={error} onRetry={reload} context="Could not load GitOps status" /> : null}
        {!loading && !error && rows.length === 0 ? (
          <EmptyState title="No applications reported" message="No Argo CD applications were returned for this cluster." />
        ) : null}
        {!loading && !error && rows.length > 0 ? (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(row) => `${row.namespace}/${row.name}`}
            caption="Argo CD applications"
          />
        ) : null}
      </section>
    </div>
  );
}
