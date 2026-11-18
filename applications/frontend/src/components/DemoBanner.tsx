import type { Meta } from "../lib/api";

interface DemoBannerProps {
  meta: Meta | null | undefined;
  scope?: string;
}

/**
 * Persistent reminder that the payload is not cluster data.
 * Shown whenever meta.source !== "cluster"; meta.reason is surfaced verbatim.
 */
export function DemoBanner({ meta, scope }: DemoBannerProps) {
  if (!meta || meta.source === "cluster") return null;

  const reason = meta.reason?.trim();
  return (
    <div className="demo-banner" role="status" aria-live="polite">
      <span className="demo-banner__tag">DEMO DATA</span>
      <span className="demo-banner__body">
        {scope ? <strong>{scope}: </strong> : null}
        This view is served from the platform API demo dataset (<code>meta.source={meta.source}</code>)
        — it does not reflect a live cluster.
        {reason ? <span className="demo-banner__reason"> Reason: {reason}</span> : null}
      </span>
    </div>
  );
}
