import { Building2, Phone, Zap } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { StatCard } from "@/components/shared/StatCard";
import { usePlatformMetrics } from "@/lib/platformHooks";

export default function PlatformDashboard() {
  const metrics = usePlatformMetrics();

  return (
    <div className="space-y-6">
      <PageHeader title="Platform overview" description="Cross-tenant health, at a glance." />

      {metrics.isError ? (
        <ErrorBanner error={metrics.error} onRetry={() => metrics.refetch()} />
      ) : (
        // Grid leaves room for more tiles as /api/platform/metrics grows — only
        // render cards for fields the endpoint actually returns today.
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            icon={Building2}
            label="Organizations"
            value={metrics.data?.org_count}
            loading={metrics.isLoading}
          />
          <StatCard
            icon={Zap}
            label="Active campaigns"
            value={metrics.data?.active_campaigns}
            loading={metrics.isLoading}
            tone="warning"
          />
          <StatCard
            icon={Phone}
            label="Total calls used"
            value={metrics.data?.total_calls_used?.toLocaleString()}
            loading={metrics.isLoading}
            tone="info"
          />
        </div>
      )}
    </div>
  );
}
