import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DashboardStats } from "@/lib/types";
import { CHART_AXIS_PROPS, CHART_GRID_PROPS, ChartTooltip } from "./ChartTooltip";

interface CallsByDayChartProps {
  data: DashboardStats["calls_last_7_days"];
  height?: number;
}

/** Magnitude comparison across days — a single series, so no legend box needed. */
export function CallsByDayChart({ data, height = 280 }: CallsByDayChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ left: -12, right: 8 }}>
        <CartesianGrid {...CHART_GRID_PROPS} />
        <XAxis dataKey="day" {...CHART_AXIS_PROPS} />
        <YAxis {...CHART_AXIS_PROPS} allowDecimals={false} width={32} />
        <Tooltip content={ChartTooltip} cursor={{ fill: "var(--color-muted)" }} />
        <Bar dataKey="calls" name="Calls" fill="var(--color-chart-1)" radius={[6, 6, 0, 0]} maxBarSize={40} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
