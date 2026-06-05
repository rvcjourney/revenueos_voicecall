import { createFileRoute, Link } from "@tanstack/react-router";
import { useState, useEffect, useRef } from "react";
import { Phone, Heart, Clock, TrendingUp, Play, ArrowRight, Zap as ZapIcon, Users } from "lucide-react";
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
import { authApi, adminApi, type OrgQuotaInfo, type OrgStatsOut } from "@/lib/api";

export const Route = createFileRoute("/_authed/dashboard")({
  head: () => ({ meta: [{ title: "Dashboard — MOTMVoice" }] }),
  component: Dashboard,
});

function fmtDuration(s: number) {
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}m ${String(r).padStart(2, "0")}s`;
}

// ── useCountUp ────────────────────────────────────────────────────────────────
function useCountUp(target: number, duration = 700) {
  const [count, setCount] = useState(0);
  const rafRef  = useRef(0);
  const prevRef = useRef({ target: -1, count: 0 });

  useEffect(() => {
    if (target === prevRef.current.target) return;
    const startVal  = prevRef.current.count;
    prevRef.current.target = target;
    const startTime = performance.now();
    cancelAnimationFrame(rafRef.current);
    function tick(now: number) {
      const p = Math.min((now - startTime) / duration, 1);
      const e = 1 - Math.pow(1 - p, 3);
      const n = Math.round(startVal + (target - startVal) * e);
      prevRef.current.count = n;
      setCount(n);
      if (p < 1) rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration]);

  return count;
}

// ── Skeleton helper ───────────────────────────────────────────────────────────
function Skel({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-surface-2 ${className}`} />;
}

// ── Animated KPI card ─────────────────────────────────────────────────────────
function AnimatedKPICard({
  label, rawValue, format, icon: Icon, tone, trend,
}: {
  label: string;
  rawValue: number;
  format: (n: number) => string;
  icon: React.ElementType;
  tone: string;
  trend?: number | null;
}) {
  const animated = useCountUp(rawValue);
  return (
    <div className="card-top-accent relative rounded-xl bg-card border border-border/80 p-4 hover:border-primary/25 transition-all duration-200 overflow-hidden group">
      <div className="absolute inset-0 bg-primary/0 group-hover:bg-primary/[0.02] transition-colors duration-300 pointer-events-none rounded-xl" />
      <div className="relative">
        <div className="h-9 w-9 rounded-lg bg-primary/10 grid place-items-center text-primary mb-3">
          <Icon className="h-4 w-4" />
        </div>
        <div className={`text-2xl font-bold font-mono ${tone}`}>{format(animated)}</div>
        <div className="text-xs text-muted-foreground mt-1 leading-snug">{label}</div>
        {trend !== null && trend !== undefined && (
          <div className={`flex items-center gap-0.5 text-[11px] font-medium mt-1.5 ${trend >= 0 ? "text-success" : "text-destructive"}`}>
            <span>{trend >= 0 ? "↑" : "↓"} {Math.abs(trend)}%</span>
            <span className="text-muted-foreground font-normal ml-0.5">vs yesterday</span>
          </div>
        )}
      </div>
    </div>
  );
}

function Dashboard() {
  const { user, isAdmin }   = useAuth();
  const { theme }           = useTheme();
  const { data: stats, isLoading: statsLoading } = useDashboard();
  const { data: callsData } = useCalls({ limit: 8 });
  const [orgInfo, setOrgInfo]   = useState<OrgQuotaInfo | null>(null);
  const [orgStats, setOrgStats] = useState<OrgStatsOut | null>(null);
  const [orgStatsLoading, setOrgStatsLoading] = useState(false);

  const [activePieIdx, setActivePieIdx] = useState<number | null>(null);

  useEffect(() => {
    authApi.getOrgInfo().then(({ data }) => setOrgInfo(data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    setOrgStatsLoading(true);
    adminApi.getStats().then(({ data }) => setOrgStats(data)).catch(() => {}).finally(() => setOrgStatsLoading(false));
  }, [isAdmin]);

  // Chart colours that adapt to theme
  const axisColor  = theme === "dark" ? "oklch(0.45 0.012 270)" : "oklch(0.44 0.018 270)";
  const gridColor  = theme === "dark" ? "oklch(0.16 0.012 270)" : "oklch(0.87 0.010 275)";

  const tooltipStyle: React.CSSProperties = {
    background:   "var(--card)",
    border:       "1px solid var(--border)",
    borderRadius: 10,
    color:        "var(--foreground)",
    fontSize:     12,
    boxShadow:    "var(--shadow-card)",
  };

  // Trend from last 7 days data
  const last7 = stats?.calls_last_7_days ?? [];
  const callsTrend = (() => {
    if (last7.length < 2) return null;
    const t = last7[last7.length - 1]?.calls ?? 0;
    const y = last7[last7.length - 2]?.calls ?? 0;
    return y > 0 ? Math.round(((t - y) / y) * 100) : null;
  })();
  const interestTrend = (() => {
    if (last7.length < 2) return null;
    const t = last7[last7.length - 1]?.interested ?? 0;
    const y = last7[last7.length - 2]?.interested ?? 0;
    return y > 0 ? Math.round(((t - y) / y) * 100) : null;
  })();

  const kpis = isAdmin
    ? [
        { label: "Total Calls",       rawValue: orgStats?.totals.total_calls      ?? 0, format: (n: number) => n.toLocaleString(), icon: Phone,      tone: "text-foreground", trend: callsTrend    },
        { label: "Interested Leads",  rawValue: orgStats?.totals.total_interested ?? 0, format: (n: number) => n.toLocaleString(), icon: Heart,      tone: "text-success",    trend: interestTrend },
        { label: "Active Campaigns",  rawValue: orgStats?.totals.active_campaigns ?? 0, format: (n: number) => n.toLocaleString(), icon: ZapIcon,   tone: "text-primary",    trend: null          },
        { label: "Team Members",      rawValue: orgStats?.totals.total_members    ?? 0, format: (n: number) => n.toLocaleString(), icon: Users,     tone: "text-foreground", trend: null          },
      ]
    : [
        { label: "Total Calls Today",  rawValue: stats?.kpis.calls_today     ?? 0, format: (n: number) => n.toLocaleString(), icon: Phone,      tone: "text-foreground", trend: callsTrend    },
        { label: "Interested Leads",   rawValue: stats?.kpis.interested_today ?? 0, format: (n: number) => n.toLocaleString(), icon: Heart,      tone: "text-success",    trend: interestTrend },
        { label: "Avg. Call Duration", rawValue: stats?.kpis.avg_duration_seconds ?? 0, format: fmtDuration,                   icon: Clock,      tone: "text-foreground", trend: null          },
        { label: "Pickup Rate",        rawValue: stats?.kpis.pickup_rate ?? 0, format: (n: number) => `${n}%`,                icon: TrendingUp, tone: "text-primary",    trend: null          },
      ];

  const topCampaigns = stats?.active_campaigns ?? [];
  const recent       = callsData?.items ?? [];
  const outcomes     = stats?.outcome_breakdown ?? [];

  return (
    <div className="space-y-5 max-w-[1600px]">

      {/* ── Hero banner ──────────────────────────────────────────────────── */}
      <div className="relative rounded-2xl overflow-hidden border border-border/60 bg-card p-6">
        <div className="absolute inset-0 dot-grid opacity-[0.15] pointer-events-none" />
        <div className="absolute -top-24 -right-24 w-80 h-80 rounded-full bg-primary/8 blur-3xl pointer-events-none" />
        <div className="absolute -bottom-16 -left-16 w-56 h-56 rounded-full bg-primary/5 blur-3xl pointer-events-none" />

        <div className="relative z-10 flex items-center justify-between gap-4 flex-wrap">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-[11px] font-semibold tracking-wider uppercase mb-3">
              <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
              Live Dashboard
            </div>
            <h1 className="text-[28px] font-heading font-semibold leading-tight">
              <span className="text-gradient">Welcome back,</span>{" "}
              <span className="text-foreground">{user?.full_name?.split(" ")[0] ?? "there"} 👋</span>
            </h1>
            <p className="text-sm text-muted-foreground mt-1.5">
              {new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" })}
            </p>
          </div>

          <div className="hidden lg:flex items-center gap-6">
            <div className="text-right border-r border-border/60 pr-6">
              <div className="text-[28px] font-bold font-mono text-gradient leading-none">
                {isAdmin
                  ? (orgStats?.totals.total_calls ?? 0).toLocaleString()
                  : (stats?.kpis.calls_today ?? 0).toLocaleString()}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                {isAdmin ? "Total calls (all time)" : "Calls today"}
              </div>
            </div>
            <div className="text-right">
              <div className="text-[28px] font-bold font-mono text-success leading-none">
                {isAdmin
                  ? (orgStats?.totals.total_interested ?? 0).toLocaleString()
                  : (stats?.kpis.interested_today ?? 0).toLocaleString()}
              </div>
              <div className="text-xs text-muted-foreground mt-1">Interested leads</div>
            </div>
          </div>
        </div>
      </div>

      {/* ── KPI cards ─────────────────────────────────────────────────────── */}
      {(statsLoading || (isAdmin && orgStatsLoading)) ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="rounded-xl bg-card border border-border/80 p-4">
              <Skel className="h-9 w-9 rounded-lg mb-3" />
              <Skel className="h-7 w-20 mb-2" />
              <Skel className="h-3 w-28" />
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {kpis.map((k) => (
            <AnimatedKPICard key={k.label} {...k} />
          ))}
        </div>
      )}

      {/* ── Call quota bar ────────────────────────────────────────────────── */}
      {orgInfo && orgInfo.monthly_call_quota > 0 && (
        <div className="rounded-xl bg-card border border-border/80 p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <ZapIcon className="h-4 w-4 text-primary" />
              <span className="text-sm font-semibold">Monthly Call Quota</span>
              <span className="text-xs text-muted-foreground capitalize">· {orgInfo.plan_tier} plan</span>
            </div>
            <span className="font-mono text-sm font-semibold">
              {orgInfo.calls_used_this_period.toLocaleString()}
              <span className="text-muted-foreground font-normal"> / {orgInfo.monthly_call_quota.toLocaleString()}</span>
            </span>
          </div>
          <Progress
            value={Math.min(100, (orgInfo.calls_used_this_period / orgInfo.monthly_call_quota) * 100)}
            className="h-2"
          />
          <div className="flex justify-between mt-1 text-xs text-muted-foreground">
            <span>{Math.round((orgInfo.calls_used_this_period / orgInfo.monthly_call_quota) * 100)}% used this period</span>
            <span>{(orgInfo.monthly_call_quota - orgInfo.calls_used_this_period).toLocaleString()} remaining</span>
          </div>
        </div>
      )}

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
                  <linearGradient id="primaryGrad" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%"   stopColor="oklch(0.565 0.240 284)" />
                    <stop offset="100%" stopColor="oklch(0.545 0.220 252)" />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                <XAxis dataKey="day"  stroke={axisColor} fontSize={11} tickLine={false} axisLine={false} />
                <YAxis              stroke={axisColor} fontSize={11} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ stroke: "var(--border)", strokeWidth: 1 }} />
                <Line type="monotone" dataKey="calls"      name="Total Calls" stroke="url(#primaryGrad)" strokeWidth={2.5} dot={{ r: 3, fill: "oklch(0.565 0.240 284)" }} activeDot={{ r: 5 }} />
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
                    <td colSpan={4} className="px-5 py-12 text-center">
                      <div className="inline-flex flex-col items-center gap-2">
                        <div className="h-10 w-10 rounded-xl bg-surface-2 grid place-items-center">
                          <Play className="h-5 w-5 text-muted-foreground/30" />
                        </div>
                        <p className="text-sm font-medium text-muted-foreground/70">No active campaigns</p>
                        <p className="text-xs text-muted-foreground/50">Launch a campaign to see it here</p>
                      </div>
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
              <li className="px-5 py-12 text-center">
                <div className="inline-flex flex-col items-center gap-2">
                  <div className="h-10 w-10 rounded-xl bg-surface-2 grid place-items-center">
                    <Phone className="h-5 w-5 text-muted-foreground/30" />
                  </div>
                  <p className="text-sm font-medium text-muted-foreground/70">No calls yet</p>
                  <p className="text-xs text-muted-foreground/50">Calls will appear here in real time</p>
                </div>
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
