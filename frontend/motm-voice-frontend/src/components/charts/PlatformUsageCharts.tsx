import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PlatformUsagePoint } from "@/lib/platformTypes";
import { CHART_AXIS_PROPS, CHART_GRID_PROPS, ChartTooltip } from "./ChartTooltip";

interface PlatformUsageChartProps {
  data: PlatformUsagePoint[];
  height?: number;
}

/** Magnitude comparison across days — a single series, so no legend box needed. */
export function PlatformCallsChart({ data, height = 240 }: PlatformUsageChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ left: -12, right: 8 }}>
        <CartesianGrid {...CHART_GRID_PROPS} />
        <XAxis dataKey="day" {...CHART_AXIS_PROPS} interval="preserveStartEnd" />
        <YAxis {...CHART_AXIS_PROPS} allowDecimals={false} width={32} />
        <Tooltip content={ChartTooltip} cursor={{ fill: "var(--color-muted)" }} />
        <Bar dataKey="calls" name="Calls" fill="var(--color-chart-1)" radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Trend over time: single series, filled area. */
export function PlatformCreditsChart({ data, height = 240 }: PlatformUsageChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ left: -12, right: 8 }}>
        <defs>
          <linearGradient id="platformCreditsGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-chart-2)" stopOpacity={0.28} />
            <stop offset="100%" stopColor="var(--color-chart-2)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid {...CHART_GRID_PROPS} />
        <XAxis dataKey="day" {...CHART_AXIS_PROPS} interval="preserveStartEnd" />
        <YAxis {...CHART_AXIS_PROPS} allowDecimals={false} width={32} />
        <Tooltip content={ChartTooltip} cursor={{ stroke: "var(--color-border)", strokeWidth: 1 }} />
        <Area
          type="monotone"
          dataKey="credits"
          name="Credits used"
          stroke="var(--color-chart-2)"
          fill="url(#platformCreditsGrad)"
          strokeWidth={2}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
