import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { Phone, Heart, Clock, TrendingUp, Play, ArrowRight } from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, CartesianGrid,
} from "recharts";
import { formatDuration } from "@/lib/mock-data";
import { CampaignBadge, OutcomeBadge } from "@/components/layout/StatusBadge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { useDashboard, useCalls } from "@/lib/hooks";
import { useTheme } from "@/lib/theme";

export const Route = createFileRoute("/_authed/dashboard")({
  head: () => ({ meta: [{ title: "Dashboard — MOTMVoice" }] }),
  component: Dashboard,
});

function fmtDuration(s: number) {
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}m ${String(r).padStart(2, "0")}s`;
}

function Dashboard() {
  const { user }            = useAuth();
  const { theme }           = useTheme();
  const { data: stats }     = useDashboard();
  const { data: callsData } = useCalls({ limit: 8 });

  const [activePieIdx, setActivePieIdx] = useState<number | null>(null);

  // Chart colours that adapt to theme
  const axisColor  = theme === "dark" ? "oklch(0.52 0.006 55)"  : "oklch(0.44 0.020 265)";
  const gridColor  = theme === "dark" ? "oklch(0.17 0.006 55)"  : "oklch(0.86 0.012 60)";

  const tooltipStyle: React.CSSProperties = {
    background:   "var(--card)",
    border:       "1px solid var(--border)",
    borderRadius: 10,
    color:        "var(--foreground)",
    fontSize:     12,
    boxShadow:    "var(--shadow-card)",
  };

  const kpis = [
    { label: "Total Calls Today",  value: (stats?.kpis.calls_today     ?? 0).toLocaleString(), icon: Phone,      tone: "text-foreground"  },
    { label: "Interested Leads",   value: (stats?.kpis.interested_today ?? 0).toLocaleString(), icon: Heart,      tone: "text-success"     },
    { label: "Avg. Call Duration", value: fmtDuration(stats?.kpis.avg_duration_seconds ?? 0),  icon: Clock,      tone: "text-foreground"  },
    { label: "Pickup Rate",        value: `${stats?.kpis.pickup_rate ?? 0}%`,                   icon: TrendingUp, tone: "text-primary"     },
  ];

  const topCampaigns = stats?.active_campaigns ?? [];
  const recent       = callsData?.items ?? [];
  const outcomes     = stats?.outcome_breakdown ?? [];

  return (
    <div className="space-y-5 max-w-[1600px]">

      {/* ── Hero banner ──────────────────────────────────────────────────── */}
      <div className="relative rounded-2xl overflow-hidden border border-border/60 bg-card p-6">
        {/* Dot grid texture */}
        <div className="absolute inset-0 dot-grid opacity-[0.15] pointer-events-none" />
        {/* Orange radial glow */}
        <div className="absolute -top-24 -right-24 w-80 h-80 rounded-full bg-primary/8 blur-3xl pointer-events-none" />
        <div className="absolute -bottom-16 -left-16 w-56 h-56 rounded-full bg-primary/5 blur-3xl pointer-events-none" />

        <div className="relative z-10 flex items-center justify-between gap-4 flex-wrap">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-[11px] font-semibold tracking-wider uppercase mb-3">
              <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
              Live Dashboard
            </div>
            <h1 className="text-[28px] font-bold leading-tight tracking-tight">
              <span className="text-gradient">Welcome back,</span>{" "}
              <span className="text-foreground">{user?.full_name?.split(" ")[0] ?? "there"} 👋</span>
            </h1>
            <p className="text-sm text-muted-foreground mt-1.5">
              {new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" })}
            </p>
          </div>

          {/* Quick-stat chip */}
          <div className="hidden lg:flex items-center gap-6">
            <div className="text-right border-r border-border/60 pr-6">
              <div className="text-[28px] font-bold font-mono text-gradient leading-none">
                {(stats?.kpis.calls_today ?? 0).toLocaleString()}
              </div>
              <div className="text-xs text-muted-foreground mt-1">Calls today</div>
            </div>
            <div className="text-right">
              <div className="text-[28px] font-bold font-mono text-success leading-none">
                {(stats?.kpis.interested_today ?? 0).toLocaleString()}
              </div>
              <div className="text-xs text-muted-foreground mt-1">Interested leads</div>
            </div>
          </div>
        </div>
      </div>

      {/* ── KPI cards ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {kpis.map((k) => (
          <div
            key={k.label}
            className="card-top-accent relative rounded-xl bg-card border border-border/80 p-4 hover:border-primary/25 transition-all duration-200 overflow-hidden group"
          >
            {/* Subtle glow on hover */}
            <div className="absolute inset-0 bg-primary/0 group-hover:bg-primary/[0.02] transition-colors duration-300 pointer-events-none rounded-xl" />
            <div className="relative">
              <div className="h-9 w-9 rounded-lg bg-primary/10 grid place-items-center text-primary mb-3">
                <k.icon className="h-4 w-4" />
              </div>
              <div className={`text-2xl font-bold font-mono ${k.tone}`}>{k.value}</div>
              <div className="text-xs text-muted-foreground mt-1 leading-snug">{k.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* ── Charts row ────────────────────────────────────────────────────── */}
      <div className="grid lg:grid-cols-3 gap-4">

        {/* Line chart */}
        <div className="lg:col-span-2 rounded-xl bg-card border border-border/80 p-5">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h3 className="font-semibold text-[14px]">Call Performance</h3>
              <p className="text-xs text-muted-foreground mt-0.5">Total calls vs interested leads · Last 7 days</p>
            </div>
            <Link to="/analytics" className="flex items-center gap-1 text-xs text-primary hover:opacity-80 transition-opacity">
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={stats?.calls_last_7_days ?? []}>
                <defs>
                  <linearGradient id="orangeGrad" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%"   stopColor="oklch(0.66 0.22 42)" />
                    <stop offset="100%" stopColor="oklch(0.76 0.18 62)" />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                <XAxis dataKey="day"  stroke={axisColor} fontSize={11} tickLine={false} axisLine={false} />
                <YAxis              stroke={axisColor} fontSize={11} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ stroke: "var(--border)", strokeWidth: 1 }} />
                <Line type="monotone" dataKey="calls"      name="Total Calls" stroke="url(#orangeGrad)" strokeWidth={2.5} dot={{ r: 3, fill: "oklch(0.66 0.22 42)" }} activeDot={{ r: 5 }} />
                <Line type="monotone" dataKey="interested" name="Interested"  stroke="oklch(0.70 0.16 160)" strokeWidth={2.5} dot={{ r: 3, fill: "oklch(0.70 0.16 160)" }} activeDot={{ r: 5 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Outcome pie */}
        <div className="rounded-xl bg-card border border-border/80 p-5">
          <h3 className="font-semibold text-[14px]">Outcome Breakdown</h3>
          <p className="text-xs text-muted-foreground mt-0.5">Last 30 days</p>
          <div className="h-64 mt-2">
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={outcomes}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={48}
                  outerRadius={76}
                  paddingAngle={3}
                  onMouseEnter={(_, index) => setActivePieIdx(index)}
                  onMouseLeave={() => setActivePieIdx(null)}
                >
                  {outcomes.map((e, i) => (
                    <Cell
                      key={i}
                      fill={e.color}
                      opacity={activePieIdx === null || activePieIdx === i ? 1 : 0.35}
                      stroke={activePieIdx === i ? e.color : "transparent"}
                      strokeWidth={activePieIdx === i ? 2 : 0}
                    />
                  ))}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
                <Legend
                  wrapperStyle={{ fontSize: 11 }}
                  formatter={(value, entry: any, index) => (
                    <span
                      style={{
                        color:      activePieIdx === index ? entry.color : "var(--muted-foreground)",
                        fontWeight: activePieIdx === index ? 600 : 400,
                        transition: "color 0.15s",
                      }}
                    >
                      {value}
                    </span>
                  )}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* ── Tables row ────────────────────────────────────────────────────── */}
      <div className="grid lg:grid-cols-3 gap-4">

        {/* Active campaigns */}
        <div className="lg:col-span-2 rounded-xl bg-card border border-border/80 overflow-hidden">
          <div className="px-5 py-4 flex items-center justify-between border-b border-border/60">
            <h3 className="font-semibold text-[14px]">Active Campaigns</h3>
            <Link to="/campaigns" className="flex items-center gap-1 text-xs text-primary hover:opacity-80 transition-opacity">
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground/60 bg-surface-2/30">
                  <th className="px-5 py-2.5 font-medium">Campaign</th>
                  <th className="px-5 py-2.5 font-medium">Status</th>
                  <th className="px-5 py-2.5 font-medium">Progress</th>
                  <th className="px-5 py-2.5 font-medium text-right">Interested</th>
                </tr>
              </thead>
              <tbody>
                {topCampaigns.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-5 py-10 text-center text-muted-foreground/50 text-sm">
                      No active campaigns
                    </td>
                  </tr>
                ) : (
                  topCampaigns.map((c) => (
                    <tr key={c.id} className="border-t border-border/40 hover:bg-surface-2/30 transition-colors">
                      <td className="px-5 py-3">
                        <Link to="/campaigns/$id" params={{ id: c.id }} className="font-medium hover:text-primary transition-colors">
                          {c.name}
                        </Link>
                      </td>
                      <td className="px-5 py-3"><CampaignBadge status={c.status as any} /></td>
                      <td className="px-5 py-3 min-w-[160px]">
                        <Progress value={c.total_contacts ? (c.completed_calls / c.total_contacts) * 100 : 0} className="h-1.5" />
                        <div className="text-xs text-muted-foreground mt-1 font-mono">
                          {c.completed_calls} / {c.total_contacts}
                        </div>
                      </td>
                      <td className="px-5 py-3 text-right font-mono text-success font-semibold">
                        {c.interested_count}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent calls */}
        <div className="rounded-xl bg-card border border-border/80 overflow-hidden">
          <div className="px-5 py-4 border-b border-border/60 flex items-center justify-between">
            <h3 className="font-semibold text-[14px]">Recent Calls</h3>
            <span className="flex items-center gap-1.5 text-[11px] text-success font-medium">
              <span className="h-1.5 w-1.5 rounded-full bg-success pulse-dot" />
              Live
            </span>
          </div>
          <ul className="divide-y divide-border/40 max-h-[400px] overflow-y-auto">
            {recent.length === 0 ? (
              <li className="px-5 py-10 text-center text-muted-foreground/50 text-sm">
                No calls yet
              </li>
            ) : (
              recent.map((c) => (
                <li key={c.id} className="p-4 hover:bg-surface-2/30 transition-colors">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-[13px] font-medium truncate font-mono text-foreground">
                        {c.phone_number}
                      </div>
                    </div>
                    <OutcomeBadge outcome={c.outcome as any} />
                  </div>
                  <div className="mt-1.5 flex items-center justify-between text-xs text-muted-foreground">
                    <span>{formatDuration(c.duration_seconds ?? 0)}</span>
                    <Link to="/calls/$id" params={{ id: c.id }}>
                      <Button variant="ghost" size="sm" className="h-6 text-xs px-2 gap-1 text-muted-foreground hover:text-foreground">
                        <Play className="h-2.5 w-2.5" /> Transcript
                      </Button>
                    </Link>
                  </div>
                </li>
              ))
            )}
          </ul>
        </div>

      </div>
    </div>
  );
}
