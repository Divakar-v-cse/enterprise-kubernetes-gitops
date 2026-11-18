import type { NormalisedError } from "../lib/api";

interface ErrorStateProps {
  error: NormalisedError;
  onRetry?: () => void;
  context?: string;
}

/** Renders the real failure. Demo data is never substituted here. */
export function ErrorState({ error, onRetry, context }: ErrorStateProps) {
  return (
    <div className="state state--error" role="alert">
      <div className="state__icon" aria-hidden="true">!</div>
      <h3 className="state__title">{context ?? "Request failed"}</h3>
      <p className="state__message">{error.message}</p>
      <dl className="state__meta">
        <div>
          <dt>Kind</dt>
          <dd>{error.kind}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{error.status ?? "n/a"}</dd>
        </div>
        <div>
          <dt>Code</dt>
          <dd>{error.code}</dd>
        </div>
        {error.requestId ? (
          <div>
            <dt>Request ID</dt>
            <dd>{error.requestId}</dd>
          </div>
        ) : null}
        <div className="state__meta-url">
          <dt>URL</dt>
          <dd>{error.url || "—"}</dd>
        </div>
      </dl>
      {onRetry ? (
        <button type="button" className="button button--ghost" onClick={onRetry}>
          Retry request
        </button>
      ) : null}
    </div>
  );
}
