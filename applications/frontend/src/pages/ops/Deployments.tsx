import { useState } from "react";
import { api } from "../../lib/api";
import type { DeploymentRow } from "../../lib/api";
import { useResource } from "../../lib/useApi";
import { Badge } from "../../components/Badge";
import { DataTable } from "../../components/DataTable";
import type { Column } from "../../components/DataTable";
import { DemoBanner } from "../../components/DemoBanner";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { Loading } from "../../components/Loading";
import { Pagination } from "../../components/Pagination";
import { StatCard } from "../../components/StatCard";
import { formatNumber, imageLabel, statusTone, text } from "../../lib/format";

const LIMIT = 25;

const columns: Array<Column<DeploymentRow>> = [
  { key: "name", header: "Deployment", render: (row) => <strong>{row.name}</strong> },
  { key: "namespace", header: "Namespace", render: (row) => <code>{row.namespace}</code> },
  {
    key: "ready",
    header: "Ready",
    align: "right",
    render: (row) => (
      <span className={row.ready < row.desired ? "value--warn" : "value--ok"}>
        {row.ready}/{row.desired}
      </span>
    ),
  },
  { key: "updated", header: "Updated", align: "right", render: (row) => formatNumber(row.updated) },
  { key: "available", header: "Available", align: "right", render: (row) => formatNumber(row.available) },
  { key: "strategy", header: "Strategy", render: (row) => <span className="mono-sm">{text(row.strategy)}</span> },
  { key: "images", header: "Image", render: (row) => <span className="mono-sm">{imageLabel(row.images)}</span> },
  {
    key: "conditions",
    header: "Conditions",
    render: (row) => (
      <span className="badge-row">
        {(row.conditions ?? []).map((condition) => (
          <Badge
            key={`${row.namespace}/${row.name}/${condition.type}`}
            tone={condition.status === "True" ? statusTone(condition.type === "Available" ? "Available" : "Progressing") : "warn"}
            title={`${condition.type}=${condition.status}`}
          >
            {condition.type}: {condition.status}
          </Badge>
        ))}
        {(row.conditions ?? []).length === 0 ? "—" : null}
      </span>
    ),
  },
  { key: "age", header: "Age", align: "right", render: (row) => text(row.age) },
];

export function Deployments() {
  const [namespace, setNamespace] = useState("");
  const [draft, setDraft] = useState("");
  const [offset, setOffset] = useState(0);

  const { data, meta, loading, error, reload } = useResource<DeploymentRow[]>(
    () => api.deployments({ limit: LIMIT, offset, namespace: namespace || undefined }),
    [namespace, offset],
  );

  const rows = data ?? [];
  const total = meta?.total ?? rows.length;
  const available = rows.filter((row) => row.available >= row.desired && row.desired > 0).length;
  const unavailable = rows.length - available;
  const readyReplicas = rows.reduce((sum, row) => sum + row.ready, 0);
  const desiredReplicas = rows.reduce((sum, row) => sum + row.desired, 0);

  return (
    <div className="page">
      <DemoBanner meta={meta} scope="Deployments" />

      <div className="page-head">
        <div>
          <h2 className="page-title">Deployments</h2>
          <p className="page-sub">Replica readiness and rollout conditions from /api/deployments</p>
        </div>
        <form
          className="filter-form"
          role="search"
          onSubmit={(event) => {
            event.preventDefault();
            setOffset(0);
            setNamespace(draft.trim());
          }}
        >
          <label className="sr-only" htmlFor="dep-ns">Filter deployments by namespace</label>
          <input
            id="dep-ns"
            className="input"
            placeholder="namespace"
            value={draft}
            maxLength={63}
            onChange={(event) => setDraft(event.target.value)}
          />
          <button type="submit" className="button button--sm">Apply</button>
          {namespace ? (
            <button
              type="button"
              className="button button--ghost button--sm"
              onClick={() => {
                setDraft("");
                setNamespace("");
                setOffset(0);
              }}
            >
              Clear
            </button>
          ) : null}
        </form>
      </div>

      <section className="stat-grid" aria-label="Deployment KPIs">
        <StatCard label="Deployments on page" value={formatNumber(rows.length)} hint={`${formatNumber(total)} matched`} />
        <StatCard label="Fully available" value={formatNumber(available)} tone={available === rows.length && rows.length > 0 ? "ok" : "warn"} />
        <StatCard label="Unavailable" value={formatNumber(unavailable)} tone={unavailable > 0 ? "error" : "ok"} />
        <StatCard label="Ready replicas" value={`${readyReplicas}/${desiredReplicas}`} tone={readyReplicas < desiredReplicas ? "warn" : "ok"} />
      </section>

      <section className="card" aria-labelledby="dep-table">
        <header className="card__head">
          <h3 id="dep-table" className="card__title">Deployment inventory</h3>
          <button type="button" className="button button--ghost button--sm" onClick={reload}>Refresh</button>
        </header>

        {loading ? <Loading label="Loading deployments" /> : null}
        {error ? <ErrorState error={error} onRetry={reload} context="Could not load deployments" /> : null}
        {!loading && !error && rows.length === 0 ? (
          <EmptyState
            title="No deployments found"
            message={namespace ? `Nothing returned for namespace “${namespace}”.` : "The platform API returned no deployments."}
          />
        ) : null}
        {!loading && !error && rows.length > 0 ? (
          <>
            <DataTable
              columns={columns}
              rows={rows}
              rowKey={(row) => `${row.namespace}/${row.name}`}
              caption="Kubernetes deployments"
            />
            <Pagination
              total={total}
              limit={meta?.limit ?? LIMIT}
              offset={meta?.offset ?? offset}
              onChange={setOffset}
              label="deployments"
            />
          </>
        ) : null}
      </section>
    </div>
  );
}
