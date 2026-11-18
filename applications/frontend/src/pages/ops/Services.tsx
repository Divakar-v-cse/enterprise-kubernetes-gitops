import { useState } from "react";
import { api } from "../../lib/api";
import type { ServicePort, ServiceRow } from "../../lib/api";
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
import { formatNumber, text } from "../../lib/format";

const LIMIT = 25;

function portLabel(ports: ServicePort[] | undefined): string {
  if (!ports || ports.length === 0) return "—";
  return ports
    .map((port) => `${port.port}→${port.target_port}/${port.protocol}${port.name ? ` (${port.name})` : ""}`)
    .join(", ");
}

function selectorLabel(selector: Record<string, string> | undefined): string {
  const entries = Object.entries(selector ?? {});
  if (entries.length === 0) return "—";
  return entries.slice(0, 2).map(([key, value]) => `${key}=${value}`).join(", ") + (entries.length > 2 ? "…" : "");
}

const columns: Array<Column<ServiceRow>> = [
  { key: "name", header: "Service", render: (row) => <strong>{row.name}</strong> },
  { key: "namespace", header: "Namespace", render: (row) => <code>{row.namespace}</code> },
  {
    key: "type",
    header: "Type",
    render: (row) => <Badge tone={row.type === "ClusterIP" ? "neutral" : "info"}>{text(row.type)}</Badge>,
  },
  { key: "cluster_ip", header: "Cluster IP", render: (row) => <span className="mono-sm">{text(row.cluster_ip)}</span> },
  { key: "ports", header: "Ports", render: (row) => <span className="mono-sm">{portLabel(row.ports)}</span> },
  { key: "selector", header: "Selector", render: (row) => <span className="mono-sm">{selectorLabel(row.selector)}</span> },
  { key: "age", header: "Age", align: "right", render: (row) => text(row.age) },
];

export function Services() {
  const [namespace, setNamespace] = useState("");
  const [draft, setDraft] = useState("");
  const [offset, setOffset] = useState(0);

  const { data, meta, loading, error, reload } = useResource<ServiceRow[]>(
    () => api.services({ limit: LIMIT, offset, namespace: namespace || undefined }),
    [namespace, offset],
  );

  const rows = data ?? [];
  const total = meta?.total ?? rows.length;
  const clusterIp = rows.filter((row) => row.type === "ClusterIP").length;
  const externallyExposed = rows.filter((row) => row.type !== "ClusterIP").length;
  const portCount = rows.reduce((sum, row) => sum + (row.ports?.length ?? 0), 0);
  const externalType = rows.find((row) => row.type !== "ClusterIP")?.type ?? "LoadBalancer / NodePort";

  return (
    <div className="page">
      <DemoBanner meta={meta} scope="Services" />

      <div className="page-head">
        <div>
          <h2 className="page-title">Services</h2>
          <p className="page-sub">Service discovery and port mapping from /api/services</p>
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
          <label className="sr-only" htmlFor="svc-ns">Filter services by namespace</label>
          <input
            id="svc-ns"
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

      <section className="stat-grid" aria-label="Service KPIs">
        <StatCard label="Services on page" value={formatNumber(rows.length)} hint={`${formatNumber(total)} matched`} />
        <StatCard label="ClusterIP" value={formatNumber(clusterIp)} />
        <StatCard
          label="Not ClusterIP"
          value={formatNumber(externallyExposed)}
          tone={externallyExposed > 0 ? "info" : "neutral"}
          hint={externallyExposed > 0 ? externalType : "all internal"}
        />
        <StatCard label="Exposed ports" value={formatNumber(portCount)} />
      </section>

      <section className="card" aria-labelledby="svc-table">
        <header className="card__head">
          <h3 id="svc-table" className="card__title">Service inventory</h3>
          <button type="button" className="button button--ghost button--sm" onClick={reload}>Refresh</button>
        </header>

        {loading ? <Loading label="Loading services" /> : null}
        {error ? <ErrorState error={error} onRetry={reload} context="Could not load services" /> : null}
        {!loading && !error && rows.length === 0 ? (
          <EmptyState title="No services found" message="No service objects matched this filter." />
        ) : null}
        {!loading && !error && rows.length > 0 ? (
          <>
            <DataTable
              columns={columns}
              rows={rows}
              rowKey={(row) => `${row.namespace}/${row.name}`}
              caption="Kubernetes services"
            />
            <Pagination
              total={total}
              limit={meta?.limit ?? LIMIT}
              offset={meta?.offset ?? offset}
              onChange={setOffset}
              label="services"
            />
          </>
        ) : null}
      </section>
    </div>
  );
}
