import { useEffect, useState } from "react";
import { DEFAULT_CONFIG, REQUEST_TIMEOUT_MS, api, getRuntimeConfig, normaliseError, setRuntimeConfig } from "../../lib/api";
import type { GatewayHealth, PlatformHealth, RuntimeConfig } from "../../lib/api";
import { useSettings } from "../../lib/settings";
import { Badge } from "../../components/Badge";
import { formatUptime, statusTone, text } from "../../lib/format";

type TestOutcome =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "platform"; health: PlatformHealth }
  | { kind: "gateway"; health: GatewayHealth }
  | { kind: "error"; message: string; detail?: string };

async function withDraftConfig<T>(draft: RuntimeConfig, run: () => Promise<T>): Promise<T> {
  const previous = getRuntimeConfig();
  setRuntimeConfig(draft);
  try {
    return await run();
  } finally {
    setRuntimeConfig(previous);
  }
}

export function Settings() {
  const { config, save, reset } = useSettings();
  const [draft, setDraft] = useState<RuntimeConfig>(config);
  const [saved, setSaved] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const [outcome, setOutcome] = useState<TestOutcome>({ kind: "idle" });

  useEffect(() => {
    setDraft(config);
  }, [config]);

  const docsBase = draft.apiBase.replace(/\/+$/, "");
  const gatewayDocsBase = draft.gatewayBase.replace(/\/+$/, "");
  const dirty = JSON.stringify(draft) !== JSON.stringify(config);

  const runPlatformTest = async () => {
    setOutcome({ kind: "running" });
    try {
      const health = await withDraftConfig(draft, () => api.health());
      setOutcome({ kind: "platform", health });
    } catch (error) {
      const normalised = normaliseError(error);
      setOutcome({ kind: "error", message: normalised.message, detail: `${normalised.code} · ${normalised.url}` });
    }
  };

  const runGatewayTest = async () => {
    setOutcome({ kind: "running" });
    try {
      const health = await withDraftConfig(draft, () => api.gatewayHealth());
      setOutcome({ kind: "gateway", health });
    } catch (error) {
      const normalised = normaliseError(error);
      setOutcome({ kind: "error", message: normalised.message, detail: `${normalised.code} · ${normalised.url}` });
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2 className="page-title">Settings</h2>
          <p className="page-sub">Endpoints and credentials are stored in this browser only (localStorage)</p>
        </div>
        {dirty ? <Badge tone="warn">unsaved changes</Badge> : <Badge tone="ok">saved</Badge>}
      </div>

      <div className="grid grid--two">
        <section className="card" aria-labelledby="connection">
          <header className="card__head">
            <h3 id="connection" className="card__title">Connection</h3>
            <span className="card__hint">timeout {REQUEST_TIMEOUT_MS / 1000}s</span>
          </header>
          <form
            className="form"
            onSubmit={(event) => {
              event.preventDefault();
              save(draft);
              setSaved(true);
              window.setTimeout(() => setSaved(false), 2500);
            }}
          >
            <div className="field">
              <label htmlFor="api-base">Platform API base URL</label>
              <input
                id="api-base"
                className="input"
                type="url"
                value={draft.apiBase}
                placeholder={DEFAULT_CONFIG.apiBase}
                onChange={(event) => setDraft({ ...draft, apiBase: event.target.value })}
                required
              />
              <p className="field__hint">Default <code>{DEFAULT_CONFIG.apiBase}</code> · bearer token sent as <code>Authorization</code>.</p>
            </div>

            <div className="field">
              <label htmlFor="gateway-base">API gateway base URL</label>
              <input
                id="gateway-base"
                className="input"
                type="url"
                value={draft.gatewayBase}
                placeholder={DEFAULT_CONFIG.gatewayBase}
                onChange={(event) => setDraft({ ...draft, gatewayBase: event.target.value })}
                required
              />
              <p className="field__hint">Default <code>{DEFAULT_CONFIG.gatewayBase}</code> · used by the storefront.</p>
            </div>

            <div className="field">
              <label htmlFor="token">Platform bearer token</label>
              <div className="field__row">
                <input
                  id="token"
                  className="input"
                  type={showToken ? "text" : "password"}
                  value={draft.token}
                  autoComplete="off"
                  spellCheck={false}
                  onChange={(event) => setDraft({ ...draft, token: event.target.value })}
                  placeholder={DEFAULT_CONFIG.token}
                />
                <button
                  type="button"
                  className="button button--ghost button--sm"
                  onClick={() => setShowToken((value) => !value)}
                  aria-pressed={showToken}
                >
                  {showToken ? "Hide" : "Show"}
                </button>
              </div>
              <p className="field__hint">
                Prefilled with <code>{DEFAULT_CONFIG.token}</code>. Clearing it sends unauthenticated requests, which the API rejects with 401.
              </p>
            </div>

            <div className="field">
              <label htmlFor="api-key">Gateway API key (writes)</label>
              <input
                id="api-key"
                className="input"
                type="text"
                value={draft.apiKey}
                autoComplete="off"
                spellCheck={false}
                onChange={(event) => setDraft({ ...draft, apiKey: event.target.value })}
              />
              <p className="field__hint">
                Sent as <code>X-API-Key</code> on <code>POST /api/users</code> and <code>POST /api/orders</code>. Default <code>{DEFAULT_CONFIG.apiKey}</code>.
              </p>
            </div>

            <div className="form__actions">
              <button type="submit" className="button">Save settings</button>
              <button type="button" className="button button--ghost" onClick={() => { reset(); setOutcome({ kind: "idle" }); }}>
                Reset to defaults
              </button>
              {saved ? <span className="muted" role="status">Saved to localStorage.</span> : null}
            </div>
          </form>
        </section>

        <section className="card" aria-labelledby="diagnostics">
          <header className="card__head">
            <h3 id="diagnostics" className="card__title">Connection test</h3>
          </header>
          <p className="muted">
            Tests use the values currently in the form, even before saving. The platform API
            connection test calls <code>GET /api/health</code>; the gateway test calls
            <code> GET /api/health</code> on the gateway.
          </p>
          <div className="form__actions">
            <button type="button" className="button" onClick={runPlatformTest} disabled={outcome.kind === "running"}>
              Test platform API
            </button>
            <button type="button" className="button button--ghost" onClick={runGatewayTest} disabled={outcome.kind === "running"}>
              Test gateway
            </button>
          </div>

          <div className="test-result" aria-live="polite">
            {outcome.kind === "idle" ? <p className="muted">No test run yet.</p> : null}
            {outcome.kind === "running" ? <p className="muted">Probing endpoint…</p> : null}
            {outcome.kind === "error" ? (
              <div className="state state--error state--compact" role="alert">
                <strong>Connection failed</strong>
                <p>{outcome.message}</p>
                {outcome.detail ? <p className="mono-sm muted">{outcome.detail}</p> : null}
              </div>
            ) : null}
            {outcome.kind === "platform" ? (
              <div className="state state--ok state--compact">
                <div className="badge-row">
                  <Badge tone={statusTone(outcome.health.status)}>{outcome.health.status}</Badge>
                  <Badge tone={outcome.health.cluster.connected ? "ok" : "warn"}>
                    cluster {outcome.health.cluster.connected ? "connected" : "unavailable"}
                  </Badge>
                </div>
                <dl className="facts">
                  <div><dt>Service</dt><dd>{text(outcome.health.service)}</dd></div>
                  <div><dt>Version</dt><dd>{text(outcome.health.version)}</dd></div>
                  <div><dt>Uptime</dt><dd>{formatUptime(outcome.health.uptime_seconds)}</dd></div>
                  <div><dt>Auth enabled</dt><dd>{outcome.health.auth_enabled ? "yes" : "no"}</dd></div>
                  <div><dt>Data source</dt><dd><code>{outcome.health.cluster.data_source}</code></dd></div>
                  <div><dt>Cluster</dt><dd>{text(outcome.health.cluster.name)}</dd></div>
                  {outcome.health.cluster.error ? (
                    <div className="facts__wide"><dt>Cluster error</dt><dd>{outcome.health.cluster.error}</dd></div>
                  ) : null}
                </dl>
              </div>
            ) : null}
            {outcome.kind === "gateway" ? (
              <div className="state state--ok state--compact">
                <div className="badge-row">
                  <Badge tone={statusTone(outcome.health.status)}>gateway {outcome.health.status}</Badge>
                  <span className="muted">v{outcome.health.version}</span>
                </div>
                <ul className="inline-list">
                  {Object.entries(outcome.health.dependencies).map(([name, dependency]) => (
                    <li key={name}>
                      <Badge tone={statusTone(dependency.status)}>{dependency.status}</Badge>{" "}
                      <code>{name}</code> — {dependency.latency_ms} ms
                      {dependency.error ? <span className="muted"> · {dependency.error}</span> : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </section>
      </div>

      <section className="card" aria-labelledby="demo-mode">
        <header className="card__head">
          <h3 id="demo-mode" className="card__title">Demo mode</h3>
        </header>
        <p>
          The platform API is read-only and never fakes a live cluster. When the Kubernetes API
          is unreachable (or <code>PLATFORM_DEMO_MODE=true</code>), responses are served from a
          fixture dataset and every payload carries <code>meta.source="demo"</code> plus a
          <code> meta.reason</code>. The dashboard shows a persistent amber <strong>DEMO DATA</strong>
          banner whenever <code>meta.source !== "cluster"</code>; it never relabels fixtures as live.
        </p>
        <ul className="inline-list">
          <li>The security page reports <code>meta.source="security-scan"</code> because scanner output is not cluster state.</li>
          <li>Deployment history is derived from Argo CD application status — no synthetic events.</li>
          <li>Alerts, logs and metrics are shown exactly as the API returns them.</li>
        </ul>
      </section>

      <section className="card" aria-labelledby="docs">
        <header className="card__head">
          <h3 id="docs" className="card__title">Documentation</h3>
        </header>
        <ul className="link-list">
          <li>
            <a className="link" href={`${docsBase}/api/docs`} target="_blank" rel="noreferrer">
              Platform API OpenAPI docs (Swagger UI)
            </a>{" "}
            <span className="mono-sm muted">{docsBase}/api/docs</span>
          </li>
          <li>
            <a className="link" href={`${gatewayDocsBase}/api/docs`} target="_blank" rel="noreferrer">
              API gateway OpenAPI docs
            </a>{" "}
            <span className="mono-sm muted">{gatewayDocsBase}/api/docs</span>
          </li>
          <li>
            <a className="link" href={`${docsBase}/api/openapi.json`} target="_blank" rel="noreferrer">
              Platform API OpenAPI schema (JSON)
            </a>
          </li>
          <li>
            Repository docs: <code>docs/API.md</code>, <code>docs/ARCHITECTURE.md</code>,{" "}
            <code>docs/RUNBOOK.md</code>, <code>docs/TROUBLESHOOTING.md</code>
          </li>
        </ul>
        <p className="muted">
          Settings persist under localStorage key <code>gitops-platform.settings.v1</code>.
          Nothing is written to the cluster.
        </p>
      </section>
    </div>
  );
}
