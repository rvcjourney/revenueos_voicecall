import { Clock, Heart, Phone, Users } from "lucide-react";
import { StatCard } from "@/components/shared/StatCard";
import type { DashboardStats } from "@/lib/types";
import { formatDuration } from "@/lib/utils";

interface DashboardKpiRowProps {
  kpis: DashboardStats["kpis"] | undefined;
  trend: DashboardStats["calls_last_7_days"] | undefined;
  loading?: boolean;
}

function dayOverDayDelta(trend: DashboardStats["calls_last_7_days"] | undefined, key: "calls" | "interested") {
  if (!trend || trend.length < 2) return undefined;
  const today = trend[trend.length - 1][key];
  const yesterday = trend[trend.length - 2][key];
  if (yesterday === 0) return undefined;
  return Math.round(((today - yesterday) / yesterday) * 1000) / 10;
}

export function DashboardKpiRow({ kpis, trend, loading }: DashboardKpiRowProps) {
  const callsDelta = dayOverDayDelta(trend, "calls");
  const interestedDelta = dayOverDayDelta(trend, "interested");
  const callsTrend = trend?.map((d) => d.calls);
  const interestedTrend = trend?.map((d) => d.interested);

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        icon={Phone}
        label="Calls today"
        value={kpis?.calls_today}
        loading={loading}
        trend={callsTrend}
        delta={callsDelta !== undefined ? { value: callsDelta, periodLabel: "vs yesterday" } : undefined}
      />
      <StatCard
        icon={Heart}
        label="Interested today"
        value={kpis?.interested_today}
        loading={loading}
        tone="success"
        trend={interestedTrend}
        delta={interestedDelta !== undefined ? { value: interestedDelta, periodLabel: "vs yesterday" } : undefined}
      />
      <StatCard
        icon={Clock}
        label="Avg call duration"
        value={kpis ? formatDuration(kpis.avg_duration_seconds) : undefined}
        loading={loading}
        tone="info"
      />
      <StatCard
        icon={Users}
        label="Pickup rate"
        value={kpis ? `${Math.round(kpis.pickup_rate)}%` : undefined}
        loading={loading}
        tone="warning"
      />
    </div>
  );
}
