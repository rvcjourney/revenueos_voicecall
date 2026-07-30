import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { DashboardStats } from "@/lib/types";
import { ChartTooltip } from "./ChartTooltip";
import { cn } from "@/lib/utils";

interface OutcomeDonutChartProps {
  data: DashboardStats["outcome_breakdown"];
  height?: number;
  /** Show a value+percent breakdown list beside the donut instead of just the chart. */
  detailed?: boolean;
  className?: string;
}

export function OutcomeDonutChart({ data, height = 280, detailed = false, className }: OutcomeDonutChartProps) {
  const total = data.reduce((sum, o) => sum + o.value, 0);

  return (
    <div className={cn(detailed ? "grid gap-4 sm:grid-cols-2 sm:items-center" : "", className)}>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius={detailed ? 60 : 55}
            outerRadius={detailed ? 95 : 90}
            paddingAngle={2}
            isAnimationActive={false}
          >
            {data.map((entry, i) => (
              <Cell key={i} fill={entry.color || "var(--color-chart-1)"} stroke="var(--color-card)" strokeWidth={2} />
            ))}
          </Pie>
          <Tooltip content={ChartTooltip} />
        </PieChart>
      </ResponsiveContainer>

      {detailed && (
        <div className="space-y-2">
          {data
            .slice()
            .sort((a, b) => b.value - a.value)
            .map((o) => {
              const pct = total > 0 ? Math.round((o.value / total) * 100) : 0;
              return (
                <div key={o.name} className="flex items-center justify-between gap-3 border-b border-border/60 pb-2 text-sm last:border-0">
                  <span className="flex items-center gap-2 text-muted-foreground">
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: o.color || "var(--color-chart-1)" }} />
                    {o.name}
                  </span>
                  <span className="flex items-center gap-2 font-medium text-foreground">
                    {o.value.toLocaleString()}
                    <span className="w-9 text-right text-xs font-normal text-muted-foreground">{pct}%</span>
                  </span>
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}
