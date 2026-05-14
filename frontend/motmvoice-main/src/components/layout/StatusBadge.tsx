export type CampaignStatus = "running" | "active" | "paused" | "completed" | "draft" | "scheduled" | "failed";
export type CallOutcome = "interested" | "completed" | "not_interested" | "no_answer" | "failed" | "in_progress" | "pending";

const outcomeStyles: Record<string, string> = {
  interested: "bg-success/15 text-success border-success/30",
  completed: "bg-primary/15 text-primary border-primary/30",
  not_interested: "bg-muted text-muted-foreground border-border",
  no_answer: "bg-surface-3 text-muted-foreground border-border",
  failed: "bg-destructive/15 text-destructive border-destructive/30",
  in_progress: "bg-warning/15 text-warning border-warning/30",
  pending: "bg-surface-3 text-muted-foreground border-border",
};
const outcomeLabel: Record<string, string> = {
  interested: "Interested",
  completed: "Completed",
  not_interested: "Not Interested",
  no_answer: "No Answer",
  failed: "Failed",
  in_progress: "In Progress",
  pending: "Pending",
};

export function OutcomeBadge({ outcome }: { outcome: string }) {
  const style = outcomeStyles[outcome] ?? "bg-surface-3 text-muted-foreground border-border";
  const label = outcomeLabel[outcome] ?? outcome;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-medium ${style}`}>
      {outcome === "in_progress" && <span className="h-1.5 w-1.5 rounded-full bg-warning animate-pulse" />}
      {label}
    </span>
  );
}

const campStyles: Record<string, string> = {
  running: "bg-success/15 text-success border-success/30",
  active: "bg-success/15 text-success border-success/30",
  paused: "bg-warning/15 text-warning border-warning/30",
  completed: "bg-primary/15 text-primary border-primary/30",
  draft: "bg-muted text-muted-foreground border-border",
  scheduled: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  failed: "bg-destructive/15 text-destructive border-destructive/30",
};

export function CampaignBadge({ status }: { status: string }) {
  const style = campStyles[status] ?? "bg-muted text-muted-foreground border-border";
  const isLive = status === "running" || status === "active";
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-medium capitalize ${style}`}>
      {isLive && <span className="h-1.5 w-1.5 rounded-full bg-success pulse-dot" />}
      {status}
    </span>
  );
}
