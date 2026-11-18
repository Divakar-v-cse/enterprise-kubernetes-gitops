import { api } from "../../lib/api";
import type {
  DeploymentRow,
  Envelope,
  GitOpsApplication,
  Meta,
} from "../../lib/api";
import { useResource } from "../../lib/useApi";
import { Badge } from "../../components/Badge";
import { DemoBanner } from "../../components/DemoBanner";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { Loading } from "../../components/Loading";
import { StatCard } from "../../components/StatCard";
import { formatDateTime, formatNumber, relativeTime, statusTone, text } from "../../lib/format";

interface TimelineEntry {
  id: string;
  at: string;
  application: string;
  revision: string;
  path: string;
  syncStatus: string;
  healthStatus: string;
  autoSync: boolean;
  namespace: string;
  rollout: DeploymentRow | undefined;
}

interface HistoryPayload {
  entries: TimelineEntry[];
  gitopsMeta: Meta;
  deploymentCount: number;
  applicationsWithoutSync: string[];
}

/**
 * Deployment history is *derived*: one entry per Argo CD application using the
 * last_synced_at / revision / sync + health state the API returned. No synthetic
 * events or invented timestamps.
 */
async function loadHistory(): Promise<Envelope<HistoryPayload>> {
  const [gitops, deployments] = await Promise.all([
    api.gitops(),
    api.deployments({ limit: 200 }),
  ]);

  const deploymentIndex = new Map<string, DeploymentRow>();
  for (const deployment of deployments.data) {
    deploymentIndex.set(`${deployment.namespace}/${deployment.name}`, deployment);
    deploymentIndex.set(deployment.name, deployment);
  }

  const withSync: TimelineEntry[] = [];
  const withoutSync: string[] = [];

  for (const application of gitops.data as GitOpsApplication[]) {
    const deployment =
      deploymentIndex.get(`${application.destination_namespace}/${application.name}`) ??
      deploymentIndex.get(application.name);
    if (!application.last_synced_at) {
      withoutSync.push(application.name);
      continue;
    }
    withSync.push({
      id: `${application.namespace}/${application.name}/${application.last_synced_at}`,
      at: application.last_synced_at,
      application: application.name,
      revision: application.revision,
      path: application.path,
      syncStatus: application.sync_status,
      healthStatus: application.health_status,
      autoSync: application.auto_sync,
      namespace: application.destination_namespace,
      rollout: deployment,
    });
  }

  withSync.sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());

  return {
    data: {
      entries: withSync,
      gitopsMeta: gitops.meta,
      deploymentCount: deployments.data.length,
      applicationsWithoutSync: withoutSync,
    },
    meta: gitops.meta,
  };
}

export function History() {
  const { data, meta, loading, error, reload } = useResource<HistoryPayload>(() => loadHistory(), []);

  const entries = data?.entries ?? [];
  const newest = entries[0];
  const oldest = entries[entries.length - 1];
  const outOfSync = entries.filter((entry) => entry.syncStatus !== "Synced").length;
  const progressing = entries.filter((entry) => entry.healthStatus !== "Healthy").length;

  return (
    <div className="page">
      <DemoBanner meta={meta} scope="Deployment history" />

      <div className="page-head">
        <div>
          <h2 className="page-title">Deployment history</h2>
          <p className="page-sub">
            Derived from Argo CD application status · {formatNumber(entries.length)} observations
          </p>
        </div>
        <button type="button" className="button button--ghost button--sm" onClick={reload}>Refresh</button>
      </div>

      <section className="callout" role="note">
        <strong>How this timeline is built.</strong> Each row is one Argo CD application:
        its <code>last_synced_at</code> timestamp, <code>revision</code>, sync status and health
        status, joined with the matching Deployment's replica readiness. The platform API does
        not expose a historical event feed, so nothing outside these API fields is shown.
      </section>

      {loading ? <Loading label="Deriving deployment history" rows={6} /> : null}
      {error ? <ErrorState error={error} onRetry={reload} context="Could not derive deployment history" /> : null}

      {data && !loading && !error ? (
        <>
          <section className="stat-grid" aria-label="History KPIs">
            <StatCard label="Observations" value={formatNumber(entries.length)} hint={`${data.deploymentCount} deployments joined`} />
            <StatCard
              label="Most recent sync"
              value={newest ? relativeTime(newest.at) : "—"}
              hint={newest ? `${newest.application} · ${newest.revision}` : "no sync timestamps"}
            />
            <StatCard
              label="Out of sync at last sync"
              value={formatNumber(outOfSync)}
              tone={outOfSync > 0 ? "warn" : "ok"}
            />
            <StatCard
              label="Unhealthy at last sync"
              value={formatNumber(progressing)}
              tone={progressing > 0 ? "warn" : "ok"}
              hint={oldest ? `oldest ${relativeTime(oldest.at)}` : undefined}
            />
          </section>

          {entries.length === 0 ? (
            <EmptyState
              title="No sync timestamps returned"
              message="Argo CD did not report last_synced_at for any application, so no timeline can be derived."
            />
          ) : (
            <section className="card" aria-labelledby="timeline">
              <header className="card__head">
                <h3 id="timeline" className="card__title">Sync observations</h3>
                <span className="card__hint">Newest first</span>
              </header>
              <ol className="timeline">
                {entries.map((entry) => (
                  <li className="timeline__item" key={entry.id}>
                    <span className="timeline__marker" aria-hidden="true" />
                    <div className="timeline__body">
                      <div className="timeline__top">
                        <div>
                          <strong>{entry.application}</strong>{" "}
                          <span className="muted">·</span>{" "}
                          <code>{text(entry.revision)}</code>{" "}
                          <span className="muted">in</span>{" "}
                          <code>{text(entry.namespace)}</code>
                        </div>
                        <div className="badge-row">
                          <Badge tone={statusTone(entry.syncStatus)}>{entry.syncStatus}</Badge>
                          <Badge tone={statusTone(entry.healthStatus)}>{entry.healthStatus}</Badge>
                          <Badge tone={entry.autoSync ? "ok" : "warn"}>
                            {entry.autoSync ? "auto-sync" : "manual"}
                          </Badge>
                        </div>
                      </div>
                      <div className="timeline__meta">
                        <span title={formatDateTime(entry.at)}>{formatDateTime(entry.at)}</span>
                        <span className="muted">({relativeTime(entry.at)})</span>
                        <span className="mono-sm">{entry.path}</span>
                        {entry.rollout ? (
                          <span className="mono-sm">
                            rollout {entry.rollout.ready}/{entry.rollout.desired} ready ·{" "}
                            {entry.rollout.strategy}
                          </span>
                        ) : (
                          <span className="mono-sm muted">no matching deployment</span>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {data.applicationsWithoutSync.length > 0 ? (
            <section className="card" aria-labelledby="no-sync">
              <header className="card__head">
                <h3 id="no-sync" className="card__title">Applications without a sync timestamp</h3>
              </header>
              <p className="muted">
                These applications reported no <code>last_synced_at</code>, so they cannot be
                placed on the timeline: <code>{data.applicationsWithoutSync.join(", ")}</code>
              </p>
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
