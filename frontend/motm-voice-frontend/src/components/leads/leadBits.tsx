import type { LeadPriority } from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";

const PRIORITY_STYLE: Record<LeadPriority, string> = {
  hot: "border-destructive/40 bg-destructive/10 text-destructive",
  warm: "border-warning/40 bg-warning/10 text-warning",
  cold: "border-border bg-muted text-muted-foreground",
};

export function PriorityBadge({ priority }: { priority: LeadPriority | null }) {
  if (!priority) return null;
  return (
    <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize", PRIORITY_STYLE[priority])}>
      {priority}
    </span>
  );
}

/** "Overdue" before today, "Today" today, else the date — local days, like the follow-up filter. */
export function followUpState(at: string | null): "overdue" | "today" | "later" | null {
  if (!at) return null;
  const d = new Date(at);
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return d < start ? "overdue" : d < end ? "today" : "later";
}

export function FollowUpText({ at }: { at: string }) {
  const state = followUpState(at);
  return (
    <span className={cn(state === "overdue" && "font-medium text-destructive", state === "today" && "font-medium text-warning")}>
      {state === "overdue" ? `Overdue · ${formatDate(at)}` : state === "today" ? "Today" : formatDate(at)}
    </span>
  );
}

/** <input type="date"> value (local day) for an ISO time, and back (10:00 local on that day). */
export const toDateInput = (iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
export const fromDateInput = (day: string) => (day ? new Date(`${day}T10:00`).toISOString() : null);
