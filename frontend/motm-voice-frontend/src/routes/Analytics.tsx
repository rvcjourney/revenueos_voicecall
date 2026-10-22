import { Calendar } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { DashboardKpiRow } from "@/components/dashboard/DashboardKpiRow";
import { OutcomeBreakdownCard } from "@/components/dashboard/OutcomeBreakdownCard";
import { CampaignComparisonTable } from "@/components/analytics/CampaignComparisonTable";
import { InterestedRateChart } from "@/components/charts/InterestedRateChart";
import { CallsByDayChart } from "@/components/charts/CallsByDayChart";
import { OutcomeDonutChart } from "@/components/charts/OutcomeDonutChart";
import { ChartZoomButton } from "@/components/charts/ChartZoomButton";
import { useCampaigns, useDashboard } from "@/lib/hooks";

export default function Analytics() {
  const dashboard = useDashboard();
  const campaigns = useCampaigns();

  return (
    <div className="space-y-8">
      <PageHeader
        title="Analytics"
        description="Deeper performance insights across all campaigns"
        actions={
          <div className="flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-sm text-muted-foreground">
            <Calendar className="h-3.5 w-3.5" /> Last 7 days
          </div>
        }
      />

      {dashboard.isError && <ErrorBanner error={dashboard.error} onRetry={() => dashboard.refetch()} />}

      <DashboardKpiRow kpis={dashboard.data?.kpis} trend={dashboard.data?.calls_last_7_days} loading={dashboard.isLoading} />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-start justify-between">
            <div>
              <CardTitle>Interested rate trend</CardTitle>
              <p className="text-sm text-muted-foreground">Interested ÷ total calls, per day</p>
            </div>
            {dashboard.data && dashboard.data.calls_last_7_days.length > 0 && (
              <ChartZoomButton title="Interested rate trend" description="Interested ÷ total calls, per day">
                <InterestedRateChart data={dashboard.data.calls_last_7_days} height={480} />
              </ChartZoomButton>
            )}
          </CardHeader>
          <CardContent className="pt-0">
            {dashboard.isLoading ? (
              <Skeleton className="h-60 w-full" />
            ) : dashboard.data && dashboard.data.calls_last_7_days.length > 0 ? (
              <InterestedRateChart data={dashboard.data.calls_last_7_days} />
            ) : (
              <EmptyState title="No data yet" description="Interested-rate trend will appear once calls start completing." />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-start justify-between">
            <div>
              <CardTitle>Call volume by day</CardTitle>
              <p className="text-sm text-muted-foreground">Total dials, last 7 days</p>
            </div>
            {dashboard.data && dashboard.data.calls_last_7_days.length > 0 && (
              <ChartZoomButton title="Call volume by day" description="Total dials, last 7 days">
                <CallsByDayChart data={dashboard.data.calls_last_7_days} height={480} />
              </ChartZoomButton>
            )}
          </CardHeader>
          <CardContent className="pt-0">
            {dashboard.isLoading ? (
              <Skeleton className="h-60 w-full" />
            ) : dashboard.data && dashboard.data.calls_last_7_days.length > 0 ? (
              <CallsByDayChart data={dashboard.data.calls_last_7_days} height={240} />
            ) : (
              <EmptyState title="No calls yet" description="Call volume by day will appear here." />
            )}
          </CardContent>
        </Card>
      </div>

      <div className="relative">
        <OutcomeBreakdownCard data={dashboard.data?.outcome_breakdown} loading={dashboard.isLoading} detailed />
        {dashboard.data && dashboard.data.outcome_breakdown.some((o) => o.value > 0) && (
          <ChartZoomButton
            title="Outcome breakdown"
            description="Last 30 days"
            className="absolute right-5 top-5"
          >
            <OutcomeDonutChart data={dashboard.data.outcome_breakdown} detailed height={480} />
          </ChartZoomButton>
        )}
      </div>

      <CampaignComparisonTable
        campaigns={campaigns.data}
        isLoading={campaigns.isLoading}
        isError={campaigns.isError}
        error={campaigns.error}
        onRetry={() => campaigns.refetch()}
      />
    </div>
  );
}
