import { api } from "../../lib/api";
import type { MetricsPayload } from "../../lib/api";
import { useResource } from "../../lib/useApi";
import { DataTable } from "../../components/DataTable";
import type { Column } from "../../components/DataTable";
import { DemoBanner } from "../../components/DemoBanner";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { LineChart } from "../../components/LineChart";
import { Loading } from "../../components/Loading";
import { StatCard } from "../../components/StatCard";
import { formatNumber, percent, ratioPercent } from "../../lib/format";

type TopPod = MetricsPayload["top_pods"][number];

const topPodColumns: Array<Column<TopPod>> = [
  { key: "pod", header: "Pod", render: (row) => <strong>{row.pod}</strong> },
  { key: "namespace", header: "Namespace", render: (row) => <code>{row.namespace}</code> },
  { key: "cpu", header: "CPU (m)", align: "right", render: (row) => formatNumber(row.cpu_millicores) },
  { key: "memory", header: "Memory (MiB)", align: "right", render: (row) => formatNumber(row.memory_mib) },
];

export function Monitoring() {
  const { data, meta, loading, error, reload } = useResource<MetricsPayload>(
    () => api.metrics(),
    [],
  );

  const seriesFor = (name: string) => data?.series.find((series) => series.name === name)?.points ?? [];
  const summary = data?.summary;

  return (
    <div className="page">
      <DemoBanner meta={meta} scope="Monitoring" />

      <div className="page-head">
        <div>
          <h2 className="page-title">Monitoring</h2>
          <p className="page-sub">Series returned by /api/metrics — no synthetic points are added</p>
        </div>
        <button type="button" className="button button--ghost button--sm" onClick={reload}>Refresh</button>
      </div>

      {loading ? <Loading label="Loading metrics" rows={4} /> : null}
      {error ? <ErrorState error={error} onRetry={reload} context="Could not load metrics" /> : null}

      {data && !loading && !error ? (
        <>
          <section className="stat-grid" aria-label="Metrics KPIs">
            <StatCard
              label="CPU used"
              value={`${formatNumber(summary?.cpu_millicores ?? 0)}m`}
              hint={`${summary?.nodes ?? 0} node(s) measured`}
            />
            <StatCard
              label="Memory used"
              value={`${formatNumber(summary?.memory_mib ?? 0)} MiB`}
              hint={`${formatNumber(summary?.pods_measured ?? 0)} pods measured`}
            />
            <StatCard
              label="Request rate"
              value={`${summary?.request_rate ?? 0} rps`}
              hint={`error rate ${percent(summary?.error_rate_percent ?? 0)}`}
              tone={(summary?.error_rate_percent ?? 0) > 2 ? "warn" : "neutral"}
            />
            <StatCard
              label="p95 latency"
              value={`${formatNumber(summary?.p95_latency_ms ?? 0)} ms`}
              tone={(summary?.p95_latency_ms ?? 0) > 500 ? "warn" : "ok"}
            />
          </section>

          <section className="chart-grid" aria-label="Metric time series">
            <LineChart
              title="CPU utilization"
              unit="%"
              points={seriesFor("cpu_utilization")}
              formatValue={(value) => ratioPercent(value)}
              color="var(--accent)"
            />
            <LineChart
              title="Memory utilization"
              unit="%"
              points={seriesFor("memory_utilization")}
              formatValue={(value) => ratioPercent(value)}
              color="var(--ok)"
            />
            <LineChart
              title="HTTP request rate"
              unit="req/s"
              points={seriesFor("http_request_rate")}
              formatValue={(value) => `${value}`}
              color="var(--info)"
            />
            <LineChart
              title="HTTP p95 latency"
              unit="s"
              points={seriesFor("http_p95_latency")}
              formatValue={(value) => `${(value * 1000).toFixed(0)} ms`}
              color="var(--warn)"
            />
          </section>

          <section className="card" aria-labelledby="top-pods">
            <header className="card__head">
              <h3 id="top-pods" className="card__title">Top pods by usage</h3>
              <span className="card__hint">{data.top_pods.length} pods reported</span>
            </header>
            {data.top_pods.length === 0 ? (
              <EmptyState
                title="No pod metrics"
                message="The metrics endpoint returned no pod-level samples (metrics-server may be unavailable)."
              />
            ) : (
              <DataTable
                columns={topPodColumns}
                rows={data.top_pods}
                rowKey={(row) => `${row.namespace}/${row.pod}`}
                caption="Top pods by CPU and memory"
                dense
              />
            )}
          </section>

          <section className="card" aria-labelledby="series-coverage">
            <header className="card__head">
              <h3 id="series-coverage" className="card__title">Series coverage</h3>
            </header>
            <ul className="inline-list">
              {data.series.map((series) => (
                <li key={series.name}>
                  <code>{series.name}</code> — {series.points.length} points, unit{" "}
                  <code>{series.unit}</code>
                </li>
              ))}
              {data.series.length === 0 ? <li>No series returned.</li> : null}
            </ul>
          </section>
        </>
      ) : null}
    </div>
  );
}
