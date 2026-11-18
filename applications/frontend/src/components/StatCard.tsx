import type { ReactNode } from "react";
import type { Tone } from "../lib/format";

interface StatCardProps {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: Tone;
  footer?: ReactNode;
}

/** Hero KPI tile. `value` is supplied by the page from API data only. */
export function StatCard({ label, value, hint, tone = "neutral", footer }: StatCardProps) {
  return (
    <div className={`stat-card stat-card--${tone}`}>
      <div className="stat-card__label">{label}</div>
      <div className="stat-card__value">{value}</div>
      {hint ? <div className="stat-card__hint">{hint}</div> : null}
      {footer ? <div className="stat-card__footer">{footer}</div> : null}
    </div>
  );
}
