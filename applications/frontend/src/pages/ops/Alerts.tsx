import { useState } from "react";
import { api } from "../../lib/api";
import type { AlertRow } from "../../lib/api";
import { useResource } from "../../lib/useApi";
import { Badge } from "../../components/Badge";
import { DemoBanner } from "../../components/DemoBanner";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { Loading } from "../../components/Loading";
import { StatCard } from "../../components/StatCard";
import { formatDateTime, relativeTime, severityTone, statusTone, text } from "../../lib/format";

const SEVERITIES = ["", "critical", "warning", "info"];
const STATUSES = ["", "firing", "resolved", "pending"];

export function Alerts() {
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");

  const { data, meta, loading, error, reload } = useResource<AlertRow[]>(
    () => api.alerts({ severity: severity || undefined, status: status || undefined }),
    [severity, status],
  );

  const rows = data ?? [];
  const firing = rows.filter((row) => row.status === "firing").length;
  const critical = rows.filter((row) => row.severity === "critical").length;
  const warning = rows.filter((row) => row.severity === "warning").length;

  return (
    <div className="page">
      <DemoBanner meta={meta} scope="Alerts" />

      <div className="page-head">
        <div>
          <h2 className="page-title">Alerts</h2>
          <p className="page-sub">Filter by severity and status. Runbooks point at repository documentation.</p>
        </div>
        <div className="filter-form">
          <label className="sr-only" htmlFor="alert-sev">Severity</label>
          <select
            id="alert-sev"
            className="input"
            value={severity}
            onChange={(event) => setSeverity(event.target.value)}
          >
            {SEVERITIES.map((option) => (
              <option key={option || "all"} value={option}>
                {option ? option.toUpperCase() : "All severities"}
              </option>
            ))}
          </select>
          <label className="sr-only" htmlFor="alert-status">Status</label>
          <select
            id="alert-status"
            className="input"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            {STATUSES.map((option) => (
              <option key={option || "all"} value={option}>
                {option ? option.toUpperCase() : "All statuses"}
              </option>
            ))}
          </select>
          <button type="button" className="button button--ghost button--sm" onClick={reload}>Refresh</button>
        </div>
      </div>

      <section className="stat-grid" aria-label="Alert KPIs">
        <StatCard label="Alerts returned" value={rows.length} />
        <StatCard label="Firing" value={meta?.firing ?? firing} tone={firing > 0 ? "warn" : "ok"} />
        <StatCard label="Critical" value={meta?.critical ?? critical} tone={critical > 0 ? "error" : "ok"} />
        <StatCard label="Warnings" value={warning} tone={warning > 0 ? "warn" : "neutral"} />
      </section>

      {loading ? <Loading label="Loading alerts" rows={4} /> : null}
      {error ? <ErrorState error={error} onRetry={reload} context="Could not load alerts" /> : null}

      {!loading && !error && rows.length === 0 ? (
        <EmptyState
          title="No alerts match"
          message={severity || status ? "No alert matched the selected severity/status filter." : "No alert rules are currently reported."}
        />
      ) : null}

      {!loading && !error && rows.length > 0 ? (
        <section className="alert-grid" aria-label="Alert list">
          {rows.map((alert) => (
            <article className="alert-card" key={alert.id}>
              <header className="alert-card__head">
                <div>
                  <h3 className="alert-card__title">{alert.name}</h3>
                  <p className="alert-card__service">
                    <code>{text(alert.namespace)}</code>
                    <span className="muted"> / </span>
                    {text(alert.service)}
                  </p>
                </div>
                <div className="badge-row">
                  <Badge tone={severityTone(alert.severity)}>{alert.severity}</Badge>
                  <Badge tone={statusTone(alert.status)}>{alert.status}</Badge>
                </div>
              </header>
              <p className="alert-card__summary">{alert.summary}</p>
              <p className="alert-card__description">{alert.description}</p>
              <dl className="alert-card__meta">
                <div>
                  <dt>Started</dt>
                  <dd title={formatDateTime(alert.starts_at)}>
                    {relativeTime(alert.starts_at)}
                    <span className="muted"> · {formatDateTime(alert.starts_at)}</span>
                  </dd>
                </div>
                <div>
                  <dt>Fingerprint</dt>
                  <dd>
                    <code>{alert.fingerprint}</code>
                  </dd>
                </div>
                <div className="alert-card__runbook">
                  <dt>Runbook</dt>
                  <dd>
                    {alert.runbook ? (
                      <span className="runbook">
                        <span aria-hidden="true">§</span> {alert.runbook}
                      </span>
                    ) : (
                      "—"
                    )}
                  </dd>
                </div>
              </dl>
            </article>
          ))}
        </section>
      ) : null}
    </div>
  );
}
