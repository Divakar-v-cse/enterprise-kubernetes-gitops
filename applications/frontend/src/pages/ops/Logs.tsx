import { useState } from "react";
import { api } from "../../lib/api";
import type { LogEntry } from "../../lib/api";
import { useResource } from "../../lib/useApi";
import { Badge } from "../../components/Badge";
import { DemoBanner } from "../../components/DemoBanner";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { Loading } from "../../components/Loading";
import { StatCard } from "../../components/StatCard";
import { formatDateTime, formatTime, levelTone, safeJson, text, truncate } from "../../lib/format";

const LEVELS = ["", "debug", "info", "warning", "error", "critical"];
const LIMIT = 200;

export function Logs() {
  const [namespace, setNamespace] = useState("");
  const [namespaceDraft, setNamespaceDraft] = useState("");
  const [pod, setPod] = useState("");
  const [podDraft, setPodDraft] = useState("");
  const [level, setLevel] = useState("");
  const [applied, setApplied] = useState(0);

  const { data, meta, loading, error, reload } = useResource<LogEntry[]>(
    () =>
      api.logs({
        namespace: namespace || undefined,
        pod: pod || undefined,
        level: level || undefined,
        limit: LIMIT,
      }),
    [namespace, pod, level, applied],
  );

  const rows = data ?? [];
  const errors = rows.filter((entry) => ["error", "critical"].includes(entry.level.toLowerCase())).length;
  const warnings = rows.filter((entry) => ["warning", "warn"].includes(entry.level.toLowerCase())).length;
  const services = new Set(rows.map((entry) => entry.service)).size;

  return (
    <div className="page">
      <DemoBanner meta={meta} scope="Logs" />

      <div className="page-head">
        <div>
          <h2 className="page-title">Logs</h2>
          <p className="page-sub">Newest entries from /api/logs — filter by namespace, pod or level</p>
        </div>
        <form
          className="filter-form"
          role="search"
          onSubmit={(event) => {
            event.preventDefault();
            setNamespace(namespaceDraft.trim());
            setPod(podDraft.trim());
            setApplied((value) => value + 1);
          }}
        >
          <label className="sr-only" htmlFor="log-ns">Namespace</label>
          <input
            id="log-ns"
            className="input"
            placeholder="namespace"
            value={namespaceDraft}
            maxLength={63}
            onChange={(event) => setNamespaceDraft(event.target.value)}
          />
          <label className="sr-only" htmlFor="log-pod">Pod</label>
          <input
            id="log-pod"
            className="input"
            placeholder="pod name"
            value={podDraft}
            maxLength={253}
            onChange={(event) => setPodDraft(event.target.value)}
          />
          <label className="sr-only" htmlFor="log-level">Log level</label>
          <select
            id="log-level"
            className="input"
            value={level}
            onChange={(event) => {
              setLevel(event.target.value);
              setApplied((value) => value + 1);
            }}
          >
            {LEVELS.map((option) => (
              <option key={option || "all"} value={option}>
                {option ? option.toUpperCase() : "All levels"}
              </option>
            ))}
          </select>
          <button type="submit" className="button button--sm">Apply</button>
          {namespace || pod || level ? (
            <button
              type="button"
              className="button button--ghost button--sm"
              onClick={() => {
                setNamespace("");
                setNamespaceDraft("");
                setPod("");
                setPodDraft("");
                setLevel("");
                setApplied((value) => value + 1);
              }}
            >
              Reset
            </button>
          ) : null}
        </form>
      </div>

      <section className="stat-grid" aria-label="Log KPIs">
        <StatCard label="Entries returned" value={rows.length} hint={`limit ${meta?.limit ?? LIMIT}`} />
        <StatCard label="Errors" value={errors} tone={errors > 0 ? "error" : "ok"} />
        <StatCard label="Warnings" value={warnings} tone={warnings > 0 ? "warn" : "ok"} />
        <StatCard label="Services emitting" value={services} />
      </section>

      <section className="card" aria-labelledby="log-viewer">
        <header className="card__head">
          <h3 id="log-viewer" className="card__title">Log stream</h3>
          <button type="button" className="button button--ghost button--sm" onClick={reload}>Refresh</button>
        </header>

        {loading ? <Loading label="Loading logs" rows={8} /> : null}
        {error ? <ErrorState error={error} onRetry={reload} context="Could not load logs" /> : null}
        {!loading && !error && rows.length === 0 ? (
          <EmptyState
            title="No log entries"
            message="No entries matched these filters. The log backend may be unreachable or empty."
          />
        ) : null}

        {!loading && !error && rows.length > 0 ? (
          <div className="log-viewer" role="log" aria-label="Log entries">
            <table className="log-table">
              <caption className="sr-only">Log entries with timestamp, level, source and message</caption>
              <thead>
                <tr>
                  <th scope="col">Timestamp</th>
                  <th scope="col">Level</th>
                  <th scope="col">Source</th>
                  <th scope="col">Message</th>
                  <th scope="col">Fields</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((entry, index) => (
                  <tr key={`${entry.timestamp}-${entry.service}-${index}`} className={`log-row log-row--${levelTone(entry.level)}`}>
                    <td className="log-table__time" title={formatDateTime(entry.timestamp)}>
                      {formatTime(entry.timestamp)}
                    </td>
                    <td>
                      <Badge tone={levelTone(entry.level)}>{entry.level.toUpperCase()}</Badge>
                    </td>
                    <td className="mono-sm">
                      {entry.service}
                      <br />
                      <small className="muted">
                        {text(entry.labels?.namespace)} / {text(entry.labels?.pod)}
                      </small>
                    </td>
                    <td className="log-table__message">{entry.message}</td>
                    <td className="mono-sm log-table__fields" title={JSON.stringify(entry.fields)}>
                      {entry.fields && Object.keys(entry.fields).length > 0
                        ? truncate(safeJson(entry.fields), 64)
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}
