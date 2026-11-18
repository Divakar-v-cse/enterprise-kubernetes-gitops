import { useState } from "react";
import { api } from "../../lib/api";
import type { PodContainer, PodRow } from "../../lib/api";
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
const PHASES = ["", "Running", "Pending", "Failed", "Succeeded", "Unknown"];

function podKey(pod: PodRow): string {
  return `${pod.namespace}/${pod.name}`;
}

/** "2/2" and "1/1" are ready; "0/1" and "1/2" are not. */
function isPodReady(ready: string | undefined): boolean {
  if (!ready) return false;
  const [current, total] = ready.split("/").map((part) => Number(part));
  return Number.isFinite(current) && Number.isFinite(total) && total > 0 && current === total;
}

function ContainerDetail({ containers }: { containers: PodContainer[] }) {
  if (!containers || containers.length === 0) {
    return <p className="muted">No container statuses reported for this pod.</p>;
  }
  return (
    <table className="sub-table">
      <caption className="sr-only">Containers in pod</caption>
      <thead>
        <tr>
          <th scope="col">Container</th>
          <th scope="col">Ready</th>
          <th scope="col">Restarts</th>
          <th scope="col">Image</th>
        </tr>
      </thead>
      <tbody>
        {containers.map((container) => (
          <tr key={container.name}>
            <td>{container.name}</td>
            <td>
              <Badge tone={container.ready ? "ok" : "warn"}>{container.ready ? "ready" : "not ready"}</Badge>
            </td>
            <td className={container.restarts > 0 ? "value--error" : undefined}>{formatNumber(container.restarts)}</td>
            <td className="mono-sm">{container.image}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Pods() {
  const [namespace, setNamespace] = useState("");
  const [namespaceDraft, setNamespaceDraft] = useState("");
  const [phase, setPhase] = useState("");
  const [offset, setOffset] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const { data, meta, loading, error, reload } = useResource<PodRow[]>(
    () =>
      api.pods({
        limit: LIMIT,
        offset,
        namespace: namespace || undefined,
        phase: phase || undefined,
      }),
    [namespace, phase, offset],
  );

  const rows = data ?? [];
  const total = meta?.total ?? rows.length;
  const runningCount = rows.filter((pod) => pod.phase === "Running").length;
  const restartingPods = rows.filter((pod) => pod.restarts > 0);
  const totalRestarts = rows.reduce((sum, pod) => sum + pod.restarts, 0);
  const notReady = rows.filter((pod) => !isPodReady(pod.ready) && pod.phase !== "Succeeded").length;

  const toggle = (pod: PodRow) => {
    setExpanded((current) => {
      const next = new Set(current);
      const key = podKey(pod);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const columns: Array<Column<PodRow>> = [
    {
      key: "name",
      header: "Pod",
      render: (row) => (
        <span className="pod-name">
          <strong>{row.name}</strong>
          {row.owner ? <small>owner {row.owner}</small> : null}
        </span>
      ),
    },
    { key: "namespace", header: "Namespace", render: (row) => <code>{row.namespace}</code> },
    {
      key: "phase",
      header: "Phase",
      render: (row) => <Badge tone={statusTone(row.phase)}>{row.phase}</Badge>,
    },
    {
      key: "ready",
      header: "Ready",
      align: "right",
      render: (row) => <span className={isPodReady(row.ready) ? "value--ok" : "value--warn"}>{row.ready}</span>,
    },
    {
      key: "restarts",
      header: "Restarts",
      align: "right",
      render: (row) =>
        row.restarts > 0 ? (
          <span className="restart restart--alert" title={`${row.restarts} restarts`}>
            {formatNumber(row.restarts)}
          </span>
        ) : (
          <span className="muted">0</span>
        ),
    },
    { key: "node", header: "Node", render: (row) => <span className="mono-sm">{text(row.node)}</span> },
    { key: "ip", header: "Pod IP", render: (row) => <span className="mono-sm">{text(row.ip)}</span> },
    { key: "age", header: "Age", align: "right", render: (row) => text(row.age) },
  ];

  return (
    <div className="page">
      <DemoBanner meta={meta} scope="Pods" />

      <div className="page-head">
        <div>
          <h2 className="page-title">Pods</h2>
          <p className="page-sub">Filter by namespace and phase, expand a pod for container detail</p>
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
          <label className="sr-only" htmlFor="pod-ns">Namespace</label>
          <input
            id="pod-ns"
            className="input"
            placeholder="namespace"
            value={namespaceDraft}
            maxLength={63}
            onChange={(event) => setNamespaceDraft(event.target.value)}
          />
          <label className="sr-only" htmlFor="pod-phase">Pod phase</label>
          <select
            id="pod-phase"
            className="input"
            value={phase}
            onChange={(event) => {
              setPhase(event.target.value);
              setOffset(0);
            }}
          >
            {PHASES.map((option) => (
              <option key={option || "all"} value={option}>
                {option || "All phases"}
              </option>
            ))}
          </select>
          <button type="submit" className="button button--sm">Apply</button>
          {namespace || phase ? (
            <button
              type="button"
              className="button button--ghost button--sm"
              onClick={() => {
                setNamespace("");
                setNamespaceDraft("");
                setPhase("");
                setOffset(0);
              }}
            >
              Reset
            </button>
          ) : null}
        </form>
      </div>

      <section className="stat-grid" aria-label="Pod KPIs">
        <StatCard label="Pods on page" value={formatNumber(rows.length)} hint={`${formatNumber(total)} matched`} />
        <StatCard label="Running" value={formatNumber(runningCount)} tone={runningCount === rows.length ? "ok" : "warn"} />
        <StatCard label="Total restarts" value={formatNumber(totalRestarts)} tone={totalRestarts > 0 ? "warn" : "ok"} hint={`${restartingPods.length} pod(s) restarting`} />
        <StatCard label="Not ready" value={formatNumber(notReady)} tone={notReady > 0 ? "error" : "ok"} />
      </section>

      {restartingPods.length > 0 ? (
        <section className="card card--warn" aria-labelledby="restart-callout">
          <header className="card__head">
            <h3 id="restart-callout" className="card__title">Restart hotspots</h3>
            <span className="card__hint">Pods with restartCount &gt; 0 on this page</span>
          </header>
          <ul className="inline-list">
            {restartingPods.map((pod) => (
              <li key={podKey(pod)}>
                <code>{pod.namespace}/{pod.name}</code> — {pod.restarts} restart(s)
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="card" aria-labelledby="pod-table">
        <header className="card__head">
          <h3 id="pod-table" className="card__title">Pod inventory</h3>
          <button type="button" className="button button--ghost button--sm" onClick={reload}>Refresh</button>
        </header>

        {loading ? <Loading label="Loading pods" /> : null}
        {error ? <ErrorState error={error} onRetry={reload} context="Could not load pods" /> : null}
        {!loading && !error && rows.length === 0 ? (
          <EmptyState
            title="No pods match"
            message="Try clearing the namespace or phase filter. Nothing is fabricated when the API returns no rows."
          />
        ) : null}
        {!loading && !error && rows.length > 0 ? (
          <>
            <DataTable
              columns={columns}
              rows={rows}
              rowKey={podKey}
              caption="Kubernetes pods"
              expand={{
                isExpanded: (row) => expanded.has(podKey(row)),
                onToggle: toggle,
                render: (row) => <ContainerDetail containers={row.containers} />,
                label: (row) => row.name,
              }}
            />
            <Pagination
              total={total}
              limit={meta?.limit ?? LIMIT}
              offset={meta?.offset ?? offset}
              onChange={setOffset}
              label="pods"
            />
          </>
        ) : null}
      </section>
    </div>
  );
}
