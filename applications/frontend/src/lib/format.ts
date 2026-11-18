/** Formatting helpers shared by every page. No page should hand-roll dates. */

export type Tone = "ok" | "warn" | "error" | "info" | "neutral";

const DASH = "—";

export function text(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  const str = String(value);
  return str.length ? str : DASH;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return new Intl.NumberFormat(undefined).format(value);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatShortTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const diffMs = Date.now() - date.getTime();
  const seconds = Math.round(diffMs / 1000);
  if (Math.abs(seconds) < 45) return seconds < 0 ? "just now" : `${Math.max(seconds, 0)}s ago`;
  const minutes = Math.round(seconds / 60);
  if (Math.abs(minutes) < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

export function percent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return `${value.toFixed(digits)}%`;
}

export function ratioPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatCents(cents: number | null | undefined, currency = "USD"): string {
  if (cents === null || cents === undefined || Number.isNaN(cents)) return DASH;
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(cents / 100);
  } catch {
    return `${(cents / 100).toFixed(2)} ${currency}`;
  }
}

export function formatUptime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return DASH;
  const total = Math.floor(seconds);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  return `${minutes}m ${total % 60}s`;
}

export function truncate(value: string, max = 48): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

/** Maps Kubernetes / Argo CD states onto a badge tone. */
export function statusTone(status: string | null | undefined): Tone {
  const value = (status ?? "").toLowerCase();
  if (["running", "healthy", "synced", "active", "ready", "available", "ok", "succeeded", "true", "bound", "completed"].includes(value)) {
    return "ok";
  }
  if (["pending", "progressing", "warning", "degraded", "unknown", "terminating", "suspended", "outofsync", "not ready"].includes(value)) {
    return "warn";
  }
  if (["failed", "error", "critical", "crashloopbackoff", "unhealthy", "missing", "false", "unavailable", "down"].includes(value)) {
    return "error";
  }
  return "neutral";
}

export function severityTone(severity: string | null | undefined): Tone {
  switch ((severity ?? "").toLowerCase()) {
    case "critical":
      return "error";
    case "high":
      return "warn";
    case "medium":
      return "info";
    case "low":
      return "neutral";
    default:
      return "neutral";
  }
}

export function levelTone(level: string | null | undefined): Tone {
  switch ((level ?? "").toLowerCase()) {
    case "error":
    case "critical":
      return "error";
    case "warning":
    case "warn":
      return "warn";
    case "info":
      return "info";
    case "debug":
      return "neutral";
    default:
      return "neutral";
  }
}

export function safeJson(value: Record<string, unknown>): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function imageLabel(images: string[] | undefined): string {
  if (!images || images.length === 0) return DASH;
  if (images.length === 1) return images[0];
  return `${images[0]} +${images.length - 1}`;
}
