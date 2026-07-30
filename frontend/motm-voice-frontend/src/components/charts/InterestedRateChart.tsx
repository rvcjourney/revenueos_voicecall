import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DashboardStats } from "@/lib/types";
import { CHART_AXIS_PROPS, CHART_GRID_PROPS, ChartTooltip } from "./ChartTooltip";

interface InterestedRateChartProps {
  data: DashboardStats["calls_last_7_days"];
  height?: number;
}

/** Interested ÷ total calls per day, computed client-side — a ratio trend, not a raw count. */
export function InterestedRateChart({ data, height = 240 }: InterestedRateChartProps) {
  const rateData = data.map((d) => ({
    day: d.day,
    rate: d.calls > 0 ? Math.round((d.interested / d.calls) * 1000) / 10 : 0,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={rateData} margin={{ left: -12, right: 8 }}>
        <CartesianGrid {...CHART_GRID_PROPS} />
        <XAxis dataKey="day" {...CHART_AXIS_PROPS} />
        <YAxis {...CHART_AXIS_PROPS} width={40} tickFormatter={(v) => `${v}%`} />
        <Tooltip content={ChartTooltip} cursor={{ stroke: "var(--color-border)", strokeWidth: 1 }} />
        <Line
          type="monotone"
          dataKey="rate"
          name="Interested rate"
          stroke="var(--color-chart-3)"
          strokeWidth={2}
          dot={{ r: 4, fill: "var(--color-chart-3)", strokeWidth: 2, stroke: "var(--color-card)" }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
