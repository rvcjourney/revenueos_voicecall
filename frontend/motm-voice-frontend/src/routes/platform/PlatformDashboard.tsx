import { AlertTriangle, Building2, CheckCircle2, Phone, XCircle, Zap } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { StatCard } from "@/components/shared/StatCard";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
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
        {
          label: "ElevenLabs",
          ok: health.data.elevenlabs_ok,
          detail: health.data.elevenlabs_ok ? "Reachable" : "Unreachable",
        },
      ]
    : [];

  const elevenlabsPct =
    health.data?.elevenlabs_characters_used != null && health.data?.elevenlabs_characters_limit
      ? Math.min((health.data.elevenlabs_characters_used / health.data.elevenlabs_characters_limit) * 100, 100)
      : null;

  const dbSizePct = health.data
    ? Math.min((health.data.db_size_bytes / health.data.db_size_limit_bytes) * 100, 100)
    : null;
  const dbConnPct =
    health.data && health.data.db_connections_max > 0
      ? Math.min((health.data.db_connections_current / health.data.db_connections_max) * 100, 100)
      : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>System health</CardTitle>
        <CardDescription>
          Live status, refreshed every 30s. Celery Beat (the scheduler) isn't probed here — it doesn't respond to
          pings the way worker processes do.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5 pt-0">
        {health.isError ? (
          <ErrorBanner error={health.error} onRetry={() => health.refetch()} />
        ) : health.isLoading || !health.data ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
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

            {elevenlabsPct !== null && (
              <div className="space-y-2 border-t border-border pt-4">
                <div className="flex items-center justify-between text-sm">
                  <p className="font-medium">
                    ElevenLabs character quota
                    {health.data.elevenlabs_tier && (
                      <span className="ml-2 text-xs capitalize text-muted-foreground">
                        · {health.data.elevenlabs_tier} plan
                      </span>
                    )}
                  </p>
                  <p className="text-muted-foreground">
                    {health.data.elevenlabs_characters_used!.toLocaleString()} /{" "}
                    {health.data.elevenlabs_characters_limit!.toLocaleString()} characters
                  </p>
                </div>
                <Progress value={elevenlabsPct} />
                {elevenlabsPct >= 85 && (
                  <p className="text-xs text-warning">Approaching character limit — {Math.round(elevenlabsPct)}% used</p>
                )}
              </div>
            )}

            <div className="space-y-4 border-t border-border pt-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <p className="font-medium">Database size</p>
                    <p className="text-muted-foreground">
                      {formatBytes(health.data.db_size_bytes)} / {formatBytes(health.data.db_size_limit_bytes)}
                    </p>
                  </div>
                  <Progress value={dbSizePct ?? 0} />
                  {dbSizePct !== null && dbSizePct >= 85 && (
                    <p className="text-xs text-warning">Approaching Supabase Free-tier storage cap</p>
                  )}
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <p className="font-medium">DB connections</p>
                    <p className="text-muted-foreground">
                      {health.data.db_connections_current} / {health.data.db_connections_max}
                    </p>
                  </div>
                  <Progress value={dbConnPct ?? 0} />
                </div>
              </div>

              {health.data.db_tables_missing_rls.length > 0 && (
                <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                  <p>
                    <span className="font-medium text-destructive">Row-Level Security disabled</span> on{" "}
                    {health.data.db_tables_missing_rls.length} table
                    {health.data.db_tables_missing_rls.length > 1 ? "s" : ""}:{" "}
                    <span className="text-muted-foreground">{health.data.db_tables_missing_rls.join(", ")}</span>
                  </p>
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
}
