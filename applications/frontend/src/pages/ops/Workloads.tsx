import { useState } from "react";
import { api } from "../../lib/api";
import type { WorkloadRow } from "../../lib/api";
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
const KINDS = ["", "Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"];

const columns: Array<Column<WorkloadRow>> = [
  {
    key: "kind",
    header: "Kind",
    render: (row) => <span className="mono-sm">{row.kind}</span>,
  },
  { key: "name", header: "Name", render: (row) => <strong>{row.name}</strong> },
  { key: "namespace", header: "Namespace", render: (row) => <code>{row.namespace}</code> },
  {
    key: "ready",
    header: "Ready / desired",
    align: "right",
    render: (row) => (
      <span className={row.ready < row.desired ? "value--warn" : undefined}>
        {row.ready}/{row.desired}
      </span>
    ),
  },
  {
    key: "status",
    header: "Status",
    render: (row) => <Badge tone={statusTone(row.status)}>{row.status}</Badge>,
  },
  { key: "images", header: "Image", render: (row) => <span className="mono-sm">{imageLabel(row.images)}</span> },
  { key: "age", header: "Age", align: "right", render: (row) => text(row.age) },
];

export function Workloads() {
  const [namespace, setNamespace] = useState("");
  const [namespaceDraft, setNamespaceDraft] = useState("");
  const [kind, setKind] = useState("");
  const [offset, setOffset] = useState(0);

  const { data, meta, loading, error, reload } = useResource<WorkloadRow[]>(
    () =>
      api.workloads({
        limit: LIMIT,
        offset,
        namespace: namespace || undefined,
        kind: kind || undefined,
      }),
    [namespace, kind, offset],
  );

  const rows = data ?? [];
  const total = meta?.total ?? rows.length;
  const degraded = rows.filter((row) => row.ready < row.desired).length;
  const desiredTotal = rows.reduce((sum, row) => sum + row.desired, 0);
  const readyTotal = rows.reduce((sum, row) => sum + row.ready, 0);

  return (
    <div className="page">
      <DemoBanner meta={meta} scope="Workloads" />

      <div className="page-head">
        <div>
          <h2 className="page-title">Workloads</h2>
          <p className="page-sub">Deployments, StatefulSets and DaemonSets reported by the platform API</p>
        </div>
        <form
          className="filter-form"
          role="search"
          onSubmit={(event) => {
            event.preventDefault();
            setOffset(0);
            setNamespace(namespaceDraft.trim());
          }}
        >
          <label className="sr-only" htmlFor="wl-ns">Namespace</label>
          <input
            id="wl-ns"
            className="input"
            placeholder="namespace"
            value={namespaceDraft}
            maxLength={63}
            onChange={(event) => setNamespaceDraft(event.target.value)}
          />
          <label className="sr-only" htmlFor="wl-kind">Workload kind</label>
          <select
            id="wl-kind"
            className="input"
            value={kind}
            onChange={(event) => {
              setKind(event.target.value);
              setOffset(0);
            }}
          >
            {KINDS.map((option) => (
              <option key={option || "all"} value={option}>
                {option || "All kinds"}
              </option>
            ))}
          </select>
          <button type="submit" className="button button--sm">Apply</button>
          {namespace || kind ? (
            <button
              type="button"
              className="button button--ghost button--sm"
              onClick={() => {
                setNamespace("");
                setNamespaceDraft("");
                setKind("");
                setOffset(0);
              }}
            >
              Reset
            </button>
          ) : null}
        </form>
      </div>

      <section className="stat-grid" aria-label="Workload KPIs">
        <StatCard label="Workloads on page" value={formatNumber(rows.length)} hint={`${formatNumber(total)} matched`} />
        <StatCard label="Ready replicas" value={`${readyTotal}/${desiredTotal}`} tone={readyTotal < desiredTotal ? "warn" : "ok"} />
        <StatCard label="Under-replicated" value={formatNumber(degraded)} tone={degraded > 0 ? "warn" : "ok"} />
        <StatCard label="Kinds present" value={formatNumber(new Set(rows.map((row) => row.kind)).size)} />
      </section>

      <section className="card" aria-labelledby="wl-table">
        <header className="card__head">
          <h3 id="wl-table" className="card__title">Workload inventory</h3>
          <button type="button" className="button button--ghost button--sm" onClick={reload}>Refresh</button>
        </header>

        {loading ? <Loading label="Loading workloads" /> : null}
        {error ? <ErrorState error={error} onRetry={reload} context="Could not load workloads" /> : null}
        {!loading && !error && rows.length === 0 ? (
          <EmptyState
            title="No workloads match"
            message="Adjust the namespace or kind filter, or confirm the cluster reports workloads."
          />
        ) : null}
        {!loading && !error && rows.length > 0 ? (
          <>
            <DataTable columns={columns} rows={rows} rowKey={(row) => `${row.kind}:${row.namespace}:${row.name}`} caption="Kubernetes workloads" />
            <Pagination
              total={total}
              limit={meta?.limit ?? LIMIT}
              offset={meta?.offset ?? offset}
              onChange={setOffset}
              label="workloads"
            />
          </>
        ) : null}
      </section>
    </div>
  );
}
