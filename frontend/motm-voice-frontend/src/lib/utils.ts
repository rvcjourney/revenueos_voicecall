import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRelativeTime(value: string | null | undefined) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  const diffMs = Date.now() - d.getTime();
  const diffSec = Math.round(diffMs / 1000);
  const abs = Math.abs(diffSec);
  if (abs < 60) return "just now";
  const diffMin = Math.round(diffSec / 60);
  if (Math.abs(diffMin) < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (Math.abs(diffHr) < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d ago`;
}

export function formatDuration(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

/**
 * A call's duration_seconds is sometimes missing even though the call has real
 * answered_at/ended_at timestamps (e.g. outcome set without the field being
 * backfilled). Fall back to deriving it from those timestamps so the UI shows
 * the call's actual length instead of "—" whenever the data to compute it exists.
 *
 * Deliberately keyed on answered_at, not started_at: started_at is stamped
 * when the dial attempt's row is created, which can run well before the call
 * ever connects (DNC checks, trunk/org slot waits, queue backlog). A call
 * whose SIP leg never connected has answered_at=null -- computing a fallback
 * from started_at there would show queue/ring wait time as if it were real
 * conversation length (see backend app/workers/tasks/campaign.py's own
 * _finalize, which uses the same answered_at-based measurement).
 */
export function callDurationSeconds(call: {
  duration_seconds: number | null | undefined;
  answered_at?: string | null;
  ended_at?: string | null;
}): number | null | undefined {
  if (call.duration_seconds !== null && call.duration_seconds !== undefined) return call.duration_seconds;
  if (!call.answered_at || !call.ended_at) return call.duration_seconds;
  const start = new Date(call.answered_at).getTime();
  const end = new Date(call.ended_at).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return call.duration_seconds;
  return Math.round((end - start) / 1000);
}

export function formatPhone(phone: string) {
  return phone;
}

export function initials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function titleCase(value: string) {
  return value
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
