import { useState } from "react";
import { api } from "../../lib/api";
import type { SecurityData, SecurityFinding } from "../../lib/api";
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
import { formatDateTime, formatNumber, severityTone, text } from "../../lib/format";

const LIMIT = 25;
const SEVERITIES = ["", "critical", "high", "medium", "low"];

const columns: Array<Column<SecurityFinding>> = [
  { key: "severity", header: "Severity", render: (row) => <Badge tone={severityTone(row.severity)}>{row.severity}</Badge> },
  { key: "id", header: "Rule", render: (row) => <code>{row.id}</code> },
  { key: "scanner", header: "Scanner", render: (row) => <span className="mono-sm">{row.scanner}</span> },
  { key: "resource", header: "Resource", render: (row) => <span className="mono-sm">{text(row.resource)}</span> },
  { key: "title", header: "Finding", render: (row) => <strong>{row.title}</strong> },
  { key: "remediation", header: "Remediation", render: (row) => <span className="mono-sm">{text(row.remediation)}</span> },
];

export function Security() {
  const [severity, setSeverity] = useState("");
  const [offset, setOffset] = useState(0);

  const { data, meta, loading, error, reload } = useResource<SecurityData>(
    () => api.security({ severity: severity || undefined, limit: LIMIT, offset }),
    [severity, offset],
  );

  const findings = data?.findings ?? [];
  const summary = data?.summary;
  const total = meta?.total ?? summary?.total ?? findings.length;

  return (
    <div className="page">
      <DemoBanner meta={meta} scope="Security findings" />

      <div className="page-head">
        <div>
          <h2 className="page-title">Security</h2>
          <p className="page-sub">
            Scanner findings from /api/security/findings
            {data?.generated_at ? ` · scan generated ${formatDateTime(data.generated_at)}` : ""}
          </p>
        </div>
        <div className="filter-form">
          <label className="sr-only" htmlFor="sec-sev">Severity</label>
          <select
            id="sec-sev"
            className="input"
            value={severity}
            onChange={(event) => {
              setSeverity(event.target.value);
              setOffset(0);
            }}
          >
            {SEVERITIES.map((option) => (
              <option key={option || "all"} value={option}>
                {option ? option.toUpperCase() : "All severities"}
              </option>
            ))}
          </select>
          <button type="button" className="button button--ghost button--sm" onClick={reload}>Refresh</button>
        </div>
      </div>

      {loading ? <Loading label="Loading security findings" rows={5} /> : null}
      {error ? <ErrorState error={error} onRetry={reload} context="Could not load security findings" /> : null}

      {data && !loading && !error ? (
        <>
          <section className="stat-grid stat-grid--five" aria-label="Findings by severity">
            <StatCard label="Critical" value={formatNumber(summary?.critical ?? 0)} tone={(summary?.critical ?? 0) > 0 ? "error" : "ok"} />
            <StatCard label="High" value={formatNumber(summary?.high ?? 0)} tone={(summary?.high ?? 0) > 0 ? "warn" : "ok"} />
            <StatCard label="Medium" value={formatNumber(summary?.medium ?? 0)} tone="info" />
            <StatCard label="Low" value={formatNumber(summary?.low ?? 0)} />
            <StatCard label="Total" value={formatNumber(summary?.total ?? total)} hint={`${findings.length} shown on page`} />
          </section>

          <section className="card" aria-labelledby="scanners">
            <header className="card__head">
              <h3 id="scanners" className="card__title">Scanners</h3>
              <span className="card__hint">{data.findings.length} finding(s) in page payload</span>
            </header>
            <div className="badge-row">
              {data.scanners.length > 0 ? (
                data.scanners.map((scanner) => (
                  <Badge key={scanner} tone="info">{scanner}</Badge>
                ))
              ) : (
                <span className="muted">No scanners reported.</span>
              )}
            </div>
            {data.note ? <p className="callout callout--inline">{data.note}</p> : null}
          </section>

          <section className="card" aria-labelledby="findings">
            <header className="card__head">
              <h3 id="findings" className="card__title">Findings</h3>
            </header>
            {findings.length === 0 ? (
              <EmptyState
                title="No findings match"
                message="Either the scan produced no findings for this severity, or the platform API returned an empty set."
              />
            ) : (
              <>
                <DataTable
                  columns={columns}
                  rows={findings}
                  rowKey={(row) => `${row.scanner}-${row.id}-${row.resource}`}
                  caption="Security findings"
                  dense
                />
                <Pagination
                  total={total}
                  limit={meta?.limit ?? LIMIT}
                  offset={meta?.offset ?? offset}
                  onChange={setOffset}
                  label="findings"
                />
              </>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
