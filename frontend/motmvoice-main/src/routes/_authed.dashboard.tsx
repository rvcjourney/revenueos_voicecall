import { createFileRoute, Link } from "@tanstack/react-router";
import { Phone, Heart, Clock, TrendingUp, ArrowUpRight, ArrowDownRight, Play } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend, CartesianGrid } from "recharts";
import { formatDuration } from "@/lib/mock-data";
import { CampaignBadge, OutcomeBadge } from "@/components/layout/StatusBadge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { useDashboard, useCalls } from "@/lib/hooks";

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
  const { user } = useAuth();
  const { data: stats } = useDashboard();
  const { data: callsData } = useCalls({ limit: 8 });

  const kpis = [
    { label: "Total Calls Today", value: (stats?.kpis.calls_today ?? 0).toLocaleString(), change: 0, icon: Phone },
    { label: "Interested Leads", value: (stats?.kpis.interested_today ?? 0).toLocaleString(), change: 0, icon: Heart },
    { label: "Avg. Call Duration", value: fmtDuration(stats?.kpis.avg_duration_seconds ?? 0), change: 0, icon: Clock },
    { label: "Pickup Rate", value: `${stats?.kpis.pickup_rate ?? 0}%`, change: 0, icon: TrendingUp },
  ];

  const topCampaigns = stats?.active_campaigns ?? [];
  const recent = callsData?.items ?? [];

  return (
    <div className="space-y-6 max-w-[1600px]">
      <div>
        <h1 className="text-2xl font-bold">Welcome back, {user?.full_name?.split(" ")[0] ?? "there"} 👋</h1>
        <p className="text-sm text-muted-foreground mt-1">{new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" })}</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((k) => (
          <div key={k.label} className="rounded-xl bg-card border border-border p-5 hover:border-primary/30 transition-colors">
            <div className="flex items-start justify-between">
              <div className="h-10 w-10 rounded-lg bg-primary/15 grid place-items-center text-primary">
                <k.icon className="h-5 w-5" />
              </div>
            </div>
            <div className="mt-4">
              <div className="text-2xl font-bold font-mono">{k.value}</div>
              <div className="text-xs text-muted-foreground mt-1">{k.label}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 rounded-xl bg-card border border-border p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-semibold">Calls Over Last 7 Days</h3>
              <p className="text-xs text-muted-foreground">Total calls vs interested leads</p>
            </div>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={stats?.calls_last_7_days ?? []}>
                <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.3 0.04 265)" />
                <XAxis dataKey="day" stroke="oklch(0.7 0.03 255)" fontSize={12} />
                <YAxis stroke="oklch(0.7 0.03 255)" fontSize={12} />
                <Tooltip contentStyle={{ background: "oklch(0.21 0.035 265)", border: "1px solid oklch(0.32 0.04 265)", borderRadius: 8 }} />
                <Line type="monotone" dataKey="calls" stroke="oklch(0.62 0.21 280)" strokeWidth={2.5} dot={{ r: 4 }} />
                <Line type="monotone" dataKey="interested" stroke="oklch(0.7 0.16 160)" strokeWidth={2.5} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-xl bg-card border border-border p-5">
          <h3 className="font-semibold">Outcomes Breakdown</h3>
          <p className="text-xs text-muted-foreground">Last 30 days</p>
          <div className="h-64 mt-2">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={stats?.outcome_breakdown ?? []} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80} paddingAngle={2}>
                  {(stats?.outcome_breakdown ?? []).map((e, i) => <Cell key={i} fill={e.color} />)}
                </Pie>
                <Tooltip contentStyle={{ background: "oklch(0.21 0.035 265)", border: "1px solid oklch(0.32 0.04 265)", borderRadius: 8 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 rounded-xl bg-card border border-border overflow-hidden">
          <div className="p-5 flex items-center justify-between border-b border-border">
            <h3 className="font-semibold">Active Campaigns</h3>
            <Link to="/campaigns" className="text-xs text-primary hover:underline">View all</Link>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground bg-surface-2/40">
                  <th className="px-5 py-2 font-medium">Campaign</th>
                  <th className="px-5 py-2 font-medium">Status</th>
                  <th className="px-5 py-2 font-medium">Progress</th>
                  <th className="px-5 py-2 font-medium text-right">Interested</th>
                </tr>
              </thead>
              <tbody>
                {topCampaigns.map((c) => (
                  <tr key={c.id} className="border-t border-border/60 hover:bg-surface-2/40">
                    <td className="px-5 py-3">
                      <Link to="/campaigns/$id" params={{ id: c.id }} className="font-medium hover:text-primary">{c.name}</Link>
                    </td>
                    <td className="px-5 py-3"><CampaignBadge status={c.status as any} /></td>
                    <td className="px-5 py-3 min-w-[180px]">
                      <Progress value={c.total_contacts ? (c.completed_calls / c.total_contacts) * 100 : 0} className="h-1.5" />
                      <div className="text-xs text-muted-foreground mt-1 font-mono">{c.completed_calls} / {c.total_contacts}</div>
                    </td>
                    <td className="px-5 py-3 text-right font-mono text-success">{c.interested_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-xl bg-card border border-border overflow-hidden">
          <div className="p-5 border-b border-border flex items-center justify-between">
            <h3 className="font-semibold">Recent Calls</h3>
            <span className="h-2 w-2 rounded-full bg-success animate-pulse" />
          </div>
          <ul className="divide-y divide-border/60 max-h-[420px] overflow-y-auto">
            {recent.map((c) => (
              <li key={c.id} className="p-4 hover:bg-surface-2/40">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate font-mono">{c.phone_number}</div>
                  </div>
                  <OutcomeBadge outcome={c.outcome as any} />
                </div>
                <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                  <span>{formatDuration(c.duration_seconds ?? 0)}</span>
                  <Link to="/calls/$id" params={{ id: c.id }}>
                    <Button variant="ghost" size="sm" className="h-7 text-xs">
                      <Play className="h-3 w-3" /> Transcript
                    </Button>
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
