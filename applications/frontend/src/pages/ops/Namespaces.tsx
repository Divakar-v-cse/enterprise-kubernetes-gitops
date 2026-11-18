import { useState } from "react";
import { api } from "../../lib/api";
import type { NamespaceRow } from "../../lib/api";
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
import { formatNumber, statusTone, text } from "../../lib/format";

const LIMIT = 25;

function labelSummary(labels: Record<string, string>): string {
  const entries = Object.entries(labels ?? {});
  if (entries.length === 0) return "—";
  return entries
    .slice(0, 2)
    .map(([key, value]) => `${key}=${value}`)
    .join(", ") + (entries.length > 2 ? ` +${entries.length - 2}` : "");
}

const columns: Array<Column<NamespaceRow>> = [
  { key: "name", header: "Namespace", render: (row) => <code>{row.name}</code> },
  {
    key: "status",
    header: "Status",
    render: (row) => <Badge tone={statusTone(row.status)}>{row.status}</Badge>,
  },
  { key: "pods", header: "Pods", align: "right", render: (row) => formatNumber(row.pods) },
  { key: "labels", header: "Labels", render: (row) => <span className="mono-sm">{labelSummary(row.labels)}</span> },
  { key: "age", header: "Age", align: "right", render: (row) => text(row.age) },
];

export function Namespaces() {
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [offset, setOffset] = useState(0);

  const { data, meta, loading, error, reload } = useResource<NamespaceRow[]>(
    () => api.namespaces({ limit: LIMIT, offset, q: query || undefined }),
    [query, offset],
  );

  const rows = data ?? [];
  const total = meta?.total ?? rows.length;
  const activeCount = rows.filter((row) => row.status.toLowerCase() === "active").length;
  const podsTotal = rows.reduce((sum, row) => sum + row.pods, 0);
  const emptyCount = rows.filter((row) => row.pods === 0).length;

  return (
    <div className="page">
      <DemoBanner meta={meta} scope="Namespaces" />

      <div className="page-head">
        <div>
          <h2 className="page-title">Namespaces</h2>
          <p className="page-sub">Server-side search and pagination from /api/namespaces</p>
        </div>
        <form
          className="filter-form"
          onSubmit={(event) => {
            event.preventDefault();
            setOffset(0);
            setQuery(draft.trim());
          }}
          role="search"
        >
          <label className="sr-only" htmlFor="ns-filter">Filter namespaces by name</label>
          <input
            id="ns-filter"
            className="input"
            placeholder="Filter by name…"
            value={draft}
            maxLength={63}
            onChange={(event) => setDraft(event.target.value)}
          />
          <button type="submit" className="button button--sm">Apply</button>
          {query ? (
            <button
              type="button"
              className="button button--ghost button--sm"
              onClick={() => {
                setDraft("");
                setQuery("");
                setOffset(0);
              }}
            >
              Clear
            </button>
          ) : null}
        </form>
      </div>

      <section className="stat-grid" aria-label="Namespace KPIs">
        <StatCard label="Namespaces (page)" value={formatNumber(rows.length)} hint={`${formatNumber(total)} matched by filter`} />
        <StatCard label="Active" value={formatNumber(activeCount)} tone={activeCount === rows.length ? "ok" : "warn"} />
        <StatCard label="Pods across page" value={formatNumber(podsTotal)} />
        <StatCard label="Empty namespaces" value={formatNumber(emptyCount)} tone={emptyCount > 0 ? "neutral" : "ok"} />
      </section>

      <section className="card" aria-labelledby="ns-table">
        <header className="card__head">
          <h3 id="ns-table" className="card__title">Namespace inventory</h3>
          <button type="button" className="button button--ghost button--sm" onClick={reload}>Refresh</button>
        </header>

        {loading ? <Loading label="Loading namespaces" /> : null}
        {error ? <ErrorState error={error} onRetry={reload} context="Could not load namespaces" /> : null}
        {!loading && !error && rows.length === 0 ? (
          <EmptyState
            title="No namespaces match"
            message={query ? `No namespace matched “${query}”.` : "The platform API returned no namespaces."}
          />
        ) : null}
        {!loading && !error && rows.length > 0 ? (
          <>
            <DataTable columns={columns} rows={rows} rowKey={(row) => row.name} caption="Kubernetes namespaces" />
            <Pagination
              total={total}
              limit={meta?.limit ?? LIMIT}
              offset={meta?.offset ?? offset}
              onChange={setOffset}
              label="namespaces"
            />
          </>
        ) : null}
      </section>
    </div>
  );
}
