import { AlertTriangle, CalendarClock, CheckCircle2, Flame, Percent, Sparkles, Trophy, Users } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LEAD_STATUSES, type LeadFilters, type LeadListResponse, type LeadStatus } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";

// ── date range ───────────────────────────────────────────────────────────────

export type RangePreset = "all" | "today" | "7d" | "30d" | "month" | "custom";
export interface DateRange { preset: RangePreset; from: string; to: string }

const day = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** The YYYY-MM-DD bounds a range sends to the API (backend reads them as India days). */
export function rangeParams(r: DateRange): Pick<LeadFilters, "date_from" | "date_to"> {
  const now = new Date();
  const back = (n: number) => day(new Date(now.getFullYear(), now.getMonth(), now.getDate() - n));
  switch (r.preset) {
    case "today": return { date_from: day(now), date_to: day(now) };
    case "7d": return { date_from: back(6), date_to: day(now) };
    case "30d": return { date_from: back(29), date_to: day(now) };
    case "month": return { date_from: day(new Date(now.getFullYear(), now.getMonth(), 1)), date_to: day(now) };
    case "custom": return { date_from: r.from || undefined, date_to: r.to || undefined };
    default: return {};
  }
}

export function DateRangePicker({ value, onChange }: { value: DateRange; onChange: (r: DateRange) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Select value={value.preset} onValueChange={(p) => onChange({ ...value, preset: p as RangePreset })}>
        <SelectTrigger className="h-9 w-40" aria-label="Date range"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All time</SelectItem>
          <SelectItem value="today">Today</SelectItem>
          <SelectItem value="7d">Last 7 days</SelectItem>
          <SelectItem value="30d">Last 30 days</SelectItem>
          <SelectItem value="month">This month</SelectItem>
          <SelectItem value="custom">Custom…</SelectItem>
        </SelectContent>
      </Select>
      {value.preset === "custom" && (
        <>
          <Input type="date" className="h-9 w-40" aria-label="From" value={value.from} onChange={(e) => onChange({ ...value, from: e.target.value })} />
          <span className="text-xs text-muted-foreground">to</span>
          <Input type="date" className="h-9 w-40" aria-label="To" value={value.to} onChange={(e) => onChange({ ...value, to: e.target.value })} />
        </>
      )}
    </div>
  );
}

// ── KPI cards ────────────────────────────────────────────────────────────────

export type KpiFilter = Partial<Pick<LeadFilters, "status" | "follow_up" | "priority">> | "all";

export function KpiCards({ data, onPick }: { data: LeadListResponse | undefined; onPick: (f: KpiFilter) => void }) {
  const c = data?.status_counts ?? {};
  const s = data?.summary;
  const total = s?.total ?? 0;
  const won = c.won ?? 0;
  const cards = [
    { label: "Total leads", value: total, icon: Users, pick: "all" as KpiFilter },
    { label: "Interested", value: c.interested ?? 0, icon: Sparkles, pick: { status: "interested" as LeadStatus } },
    { label: "Meetings scheduled", value: c.meeting_scheduled ?? 0, icon: CalendarClock, pick: { status: "meeting_scheduled" as LeadStatus } },
    { label: "Won", value: won, icon: Trophy, pick: { status: "won" as LeadStatus } },
    { label: "Conversion", value: total ? `${((won / total) * 100).toFixed(1)}%` : "—", icon: Percent, hint: "Won ÷ total" },
    { label: "Hot leads", value: s?.hot ?? 0, icon: Flame, pick: { priority: "hot" as const } },
    { label: "Follow-ups today", value: s?.due_today ?? 0, icon: CheckCircle2, pick: { follow_up: "due_today" as const } },
    { label: "Overdue", value: s?.overdue ?? 0, icon: AlertTriangle, pick: { follow_up: "overdue" as const }, alert: (s?.overdue ?? 0) > 0 },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
      {cards.map((k) => {
        const Icon = k.icon;
        const body = (
          <CardContent className="space-y-1 p-4">
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><Icon className="h-3.5 w-3.5" />{k.label}</p>
            <p className={cn("tabular-figure text-2xl font-semibold", k.alert && "text-destructive")}>{k.value}</p>
            {k.hint && <p className="text-[11px] text-muted-foreground">{k.hint}</p>}
          </CardContent>
        );
        return k.pick ? (
          <button key={k.label} type="button" onClick={() => onPick(k.pick!)} className="text-left">
            <Card className={cn("h-full transition-colors hover:border-primary/60", k.alert && "border-destructive/50")}>{body}</Card>
          </button>
        ) : (
          <Card key={k.label}>{body}</Card>
        );
      })}
    </div>
  );
}

// ── pipeline funnel ──────────────────────────────────────────────────────────

const OPEN_STAGES = LEAD_STATUSES.filter((s) => s !== "lost" && s !== "do_not_call");

export function PipelineFunnel({
  counts, active, onPick,
}: { counts: Partial<Record<LeadStatus, number>>; active?: LeadStatus; onPick: (s: LeadStatus | undefined) => void }) {
  const max = Math.max(1, ...LEAD_STATUSES.map((s) => counts[s] ?? 0));
  const row = (s: LeadStatus, muted = false) => {
    const n = counts[s] ?? 0;
    return (
      <button
        key={s}
        type="button"
        onClick={() => onPick(active === s ? undefined : s)}
        className={cn("grid w-full grid-cols-[9rem_1fr_3rem] items-center gap-3 rounded-md px-2 py-1 text-left text-xs hover:bg-muted/60", active === s && "bg-primary/10")}
        aria-pressed={active === s}
      >
        <span className={cn("truncate", active === s ? "font-semibold text-primary" : "text-muted-foreground")}>{titleCase(s)}</span>
        <span className="h-2.5 rounded-full bg-muted">
          <span className={cn("block h-full rounded-full", muted ? "bg-muted-foreground/40" : "bg-primary")} style={{ width: `${(n / max) * 100}%` }} />
        </span>
        <span className="tabular-figure text-right font-medium">{n}</span>
      </button>
    );
  };
  return (
    <Card>
      <CardContent className="space-y-1 p-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pipeline</p>
        {OPEN_STAGES.map((s) => row(s))}
        <div className="my-1 border-t border-border" />
        {row("lost", true)}
        {row("do_not_call", true)}
      </CardContent>
    </Card>
  );
}
