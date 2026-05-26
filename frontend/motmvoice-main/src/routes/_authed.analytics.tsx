import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, Legend,
  PieChart, Pie, Cell,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Calendar, Loader2 } from "lucide-react";
import { useDashboard } from "@/lib/hooks";
import { useTheme } from "@/lib/theme";

export const Route = createFileRoute("/_authed/analytics")({
  head: () => ({ meta: [{ title: "Analytics — MOTMVoice" }] }),
  component: Analytics,
});

function fmtDur(s: number | null | undefined) {
  if (!s) return "0m 00s";
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}m ${String(r).padStart(2, "0")}s`;
}

function KPI({ label, value, tone = "" }: { label: string; value: string | number; tone?: string }) {
  return (
    <div className="rounded-xl bg-card border border-border p-4">
      <div className="text-xs text-muted-foreground mb-1">{label}</div>
      <div className={`text-2xl font-bold font-mono ${tone}`}>{value}</div>
    </div>
  );
}

function Analytics() {
  const { data, isLoading } = useDashboard();
  const { theme }           = useTheme();

  // Track hovered pie slice → highlights the matching legend row
  const [activeOutcomeIdx, setActiveOutcomeIdx] = useState<number | null>(null);

  // Chart colours that adapt to theme
  const axisColor = theme === "dark" ? "oklch(0.52 0.020 265)" : "oklch(0.44 0.030 265)";
  const gridColor = theme === "dark" ? "oklch(0.20 0.030 265)" : "oklch(0.84 0.018 270)";

  // Tooltip style uses CSS variables → follows theme automatically
  const tooltipStyle: React.CSSProperties = {
    background:   "var(--card)",
    border:       "1px solid var(--border)",
    borderRadius: 8,
    color:        "var(--foreground)",
    fontSize:     12,
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const callsLast7Days  = data?.calls_last_7_days  ?? [];
  const outcomeBreakdown = data?.outcome_breakdown  ?? [];
  const activeCampaigns = data?.active_campaigns    ?? [];
  const kpis            = data?.kpis;

  const stacked = callsLast7Days.map((d) => ({
    day:        d.day,
    Interested: d.interested,
    Other:      Math.max(0, d.calls - d.interested),
  }));

  return (
    <div className="space-y-6 max-w-[1700px]">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Analytics</h1>
          <p className="text-sm text-muted-foreground mt-1">Performance & insights across all campaigns</p>
        </div>
        <Button variant="outline"><Calendar className="h-4 w-4" /> Last 7 days</Button>
      </div>

      {kpis && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPI label="Calls Today"      value={kpis.calls_today} />
          <KPI label="Interested Today" value={kpis.interested_today} tone="text-success" />
          <KPI label="Avg Duration"     value={fmtDur(kpis.avg_duration_seconds)} />
          <KPI label="Pickup Rate"      value={`${Math.round(kpis.pickup_rate ?? 0)}%`} />
        </div>
      )}

      {/* Performance line chart */}
      <div className="rounded-xl bg-card border border-border p-5">
        <h3 className="font-semibold mb-4">Performance Overview (Last 7 Days)</h3>
        <div className="h-72">
          <ResponsiveContainer>
            <LineChart data={callsLast7Days}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
              <XAxis dataKey="day" stroke={axisColor} fontSize={12} />
              <YAxis              stroke={axisColor} fontSize={12} />
              <Tooltip contentStyle={tooltipStyle} />
              <Legend />
              <Line dataKey="calls"      name="Total Calls" stroke="oklch(0.66 0.22 42)"  strokeWidth={2.5} dot={false} />
              <Line dataKey="interested" name="Interested"  stroke="oklch(0.70 0.16 160)" strokeWidth={2.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        {/* Stacked bar chart */}
        <div className="rounded-xl bg-card border border-border p-5">
          <h3 className="font-semibold mb-4">Calls by Day</h3>
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={stacked}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                <XAxis dataKey="day" stroke={axisColor} fontSize={12} />
                <YAxis              stroke={axisColor} fontSize={12} />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend />
                <Bar dataKey="Interested" stackId="a" fill="oklch(0.70 0.16 160)" />
                <Bar dataKey="Other"      stackId="a" fill="oklch(0.20 0.007 55)" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Outcome breakdown pie */}
        <div className="rounded-xl bg-card border border-border p-5">
          <h3 className="font-semibold mb-4">Outcome Breakdown</h3>
          {outcomeBreakdown.length > 0 ? (
            <div className="flex items-center gap-6">
              {/* Pie — hover sets activeOutcomeIdx */}
              <div className="h-52 flex-1">
                <ResponsiveContainer>
                  <PieChart>
                    <Pie
                      data={outcomeBreakdown}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      onMouseEnter={(_, index) => setActiveOutcomeIdx(index)}
                      onMouseLeave={() => setActiveOutcomeIdx(null)}
                    >
                      {outcomeBreakdown.map((entry, i) => (
                        <Cell
                          key={i}
                          fill={entry.color}
                          opacity={activeOutcomeIdx === null || activeOutcomeIdx === i ? 1 : 0.4}
                          stroke={activeOutcomeIdx === i ? entry.color : "transparent"}
                          strokeWidth={activeOutcomeIdx === i ? 2 : 0}
                        />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={tooltipStyle} />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              {/* Custom legend — row matching hovered slice gets coloured text */}
              <div className="space-y-2.5 text-sm min-w-0">
                {outcomeBreakdown.map((o, i) => {
                  const isActive = activeOutcomeIdx === i;
                  return (
                    <div key={i} className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full shrink-0 transition-transform duration-150"
                        style={{
                          background: o.color,
                          transform: isActive ? "scale(1.25)" : "scale(1)",
                        }}
                      />
                      <span
                        className="capitalize transition-colors duration-150"
                        style={{
                          color:      isActive ? o.color : "var(--muted-foreground)",
                          fontWeight: isActive ? 600 : 400,
                        }}
                      >
                        {o.name.replace(/_/g, " ")}
                      </span>
                      <span
                        className="font-mono ml-auto pl-3 transition-colors duration-150"
                        style={{ color: isActive ? o.color : "var(--foreground)", fontWeight: isActive ? 700 : 600 }}
                      >
                        {o.value}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-52 text-muted-foreground text-sm">
              No call data yet
            </div>
          )}
        </div>
      </div>

      {/* Campaign performance table */}
      <div className="rounded-xl bg-card border border-border overflow-hidden">
        <div className="p-5 border-b border-border">
          <h3 className="font-semibold">Active Campaigns</h3>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground bg-surface-2/40">
              <th className="px-5 py-2 font-medium">Campaign</th>
              <th className="px-5 py-2 font-medium text-right">Total</th>
              <th className="px-5 py-2 font-medium text-right">Done</th>
              <th className="px-5 py-2 font-medium text-right">Interested</th>
              <th className="px-5 py-2 font-medium text-right">Conversion</th>
            </tr>
          </thead>
          <tbody>
            {activeCampaigns.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-5 py-10 text-center text-muted-foreground text-sm">
                  No active campaigns
                </td>
              </tr>
            ) : (
              activeCampaigns.map((c) => (
                <tr key={c.id} className="border-t border-border/60 hover:bg-surface-2/40 transition-colors">
                  <td className="px-5 py-2.5 font-medium">{c.name}</td>
                  <td className="px-5 py-2.5 text-right font-mono">{c.total_contacts}</td>
                  <td className="px-5 py-2.5 text-right font-mono">{c.completed_calls}</td>
                  <td className="px-5 py-2.5 text-right font-mono text-success">{c.interested_count}</td>
                  <td className="px-5 py-2.5 text-right font-mono">
                    {c.completed_calls > 0
                      ? `${Math.round((c.interested_count / c.completed_calls) * 100)}%`
                      : "0%"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
