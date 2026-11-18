import type { ReactNode } from "react";
import type { Tone } from "../lib/format";

interface BadgeProps {
  tone?: Tone;
  children: ReactNode;
  title?: string;
  className?: string;
}

/** Small semantic pill used for sync / health / phase states. */
export function Badge({ tone = "neutral", children, title, className }: BadgeProps) {
  return (
    <span className={`badge badge--${tone}${className ? ` ${className}` : ""}`} title={title}>
      <span className="badge__dot" aria-hidden="true" />
      {children}
    </span>
  );
}
