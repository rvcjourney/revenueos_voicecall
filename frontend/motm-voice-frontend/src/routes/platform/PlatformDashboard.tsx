import { Building2, CheckCircle2, Phone, XCircle, Zap } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { StatCard } from "@/components/shared/StatCard";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { usePlatformHealth, usePlatformMetrics } from "@/lib/platformHooks";

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

      <SystemHealthCard />
    </div>
  );
}

function SystemHealthCard() {
  const health = usePlatformHealth();

  const rows: { label: string; ok: boolean; detail?: string }[] = health.data
    ? [
        { label: "API", ok: health.data.api },
        { label: "Database", ok: health.data.database },
        { label: "Redis", ok: health.data.redis },
        {
          label: "Celery workers",
          ok: health.data.celery_workers_online > 0,
          detail:
            health.data.celery_workers_online > 0
              ? `${health.data.celery_workers_online} online`
              : "No workers responding",
        },
      ]
    : [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>System health</CardTitle>
        <CardDescription>
          Live status, refreshed every 30s. Celery Beat (the scheduler) isn't probed here — it doesn't respond to
          pings the way worker processes do.
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        {health.isError ? (
          <ErrorBanner error={health.error} onRetry={() => health.refetch()} />
        ) : health.isLoading || !health.data ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {rows.map((row) => (
              <div
                key={row.label}
                className="flex items-center justify-between rounded-lg border border-border px-3 py-2.5"
              >
                <div className="flex items-center gap-2">
                  {row.ok ? (
                    <CheckCircle2 className="h-4 w-4 text-success" />
                  ) : (
                    <XCircle className="h-4 w-4 text-destructive" />
                  )}
                  <span className="text-sm font-medium">{row.label}</span>
                </div>
                <Badge variant={row.ok ? "success" : "destructive"}>
                  {row.detail ?? (row.ok ? "Operational" : "Down")}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
