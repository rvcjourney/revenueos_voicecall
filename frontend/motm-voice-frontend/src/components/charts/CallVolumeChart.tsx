import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DashboardStats } from "@/lib/types";
import { CHART_AXIS_PROPS, CHART_GRID_PROPS, ChartTooltip } from "./ChartTooltip";

interface CallVolumeChartProps {
  data: DashboardStats["calls_last_7_days"];
  height?: number;
}

/** Trend over time: total calls vs interested leads, last 7 days. */
export function CallVolumeChart({ data, height = 280 }: CallVolumeChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ left: -12, right: 8 }}>
        <defs>
          <linearGradient id="callsGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-chart-1)" stopOpacity={0.28} />
            <stop offset="100%" stopColor="var(--color-chart-1)" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="interestedGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-chart-3)" stopOpacity={0.32} />
            <stop offset="100%" stopColor="var(--color-chart-3)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid {...CHART_GRID_PROPS} />
        <XAxis dataKey="day" {...CHART_AXIS_PROPS} />
        <YAxis {...CHART_AXIS_PROPS} allowDecimals={false} width={32} />
        <Tooltip content={ChartTooltip} cursor={{ stroke: "var(--color-border)", strokeWidth: 1 }} />
        <Legend wrapperStyle={{ fontSize: 12 }} iconType="plainline" iconSize={14} />
        <Area
          type="monotone"
          dataKey="calls"
          name="Total calls"
          stroke="var(--color-chart-1)"
          fill="url(#callsGrad)"
          strokeWidth={2}
          isAnimationActive={false}
        />
        <Area
          type="monotone"
          dataKey="interested"
          name="Interested"
          stroke="var(--color-chart-3)"
          fill="url(#interestedGrad)"
          strokeWidth={2}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
