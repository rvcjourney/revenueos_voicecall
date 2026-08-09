import { useAuth } from "@/lib/auth";
import { useAdminStats, useCalls, useConcurrency, useCreditUsage, useDashboard, useOrgInfo } from "@/lib/hooks";
import { PageHeader } from "@/components/shared/PageHeader";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { QuotaConcurrencyCard } from "@/components/dashboard/QuotaConcurrencyCard";
import { TryNowCard } from "@/components/dashboard/TryNowCard";
import { ActiveCampaignsCard } from "@/components/dashboard/ActiveCampaignsCard";
import { RecentCallsCard } from "@/components/dashboard/RecentCallsCard";
import { DashboardKpiRow } from "@/components/dashboard/DashboardKpiRow";
import { CallPerformanceCard } from "@/components/dashboard/CallPerformanceCard";
import { OutcomeBreakdownCard } from "@/components/dashboard/OutcomeBreakdownCard";

export default function Dashboard() {
  const { user, isAdmin } = useAuth();
  const dashboard = useDashboard();
  const orgInfo = useOrgInfo();
  const credits = useCreditUsage();
  const concurrency = useConcurrency();
  const adminStats = useAdminStats();
  const recentCalls = useCalls({ limit: 5 });

  const today = new Date().toLocaleDateString(undefined, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="space-y-8">
      <PageHeader
        title={`Welcome back, ${user?.full_name?.split(" ")[0] ?? "there"} 👋`}
        description={today}
        actions={
          isAdmin && adminStats.data ? (
            <div className="flex gap-6 text-right">
              <div>
                <p className="font-heading text-2xl font-semibold">{adminStats.data.totals.total_calls.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Total calls (all time)</p>
              </div>
              <div>
                <p className="font-heading text-2xl font-semibold text-success">
                  {adminStats.data.totals.total_interested.toLocaleString()}
                </p>
                <p className="text-xs text-muted-foreground">Interested leads</p>
              </div>
            </div>
          ) : undefined
        }
      />

      {dashboard.isError && <ErrorBanner error={dashboard.error} onRetry={() => dashboard.refetch()} />}

      {isAdmin && <TryNowCard />}

      <section className="space-y-4">
        <h2 className="eyebrow">Needs your attention now</h2>
        <QuotaConcurrencyCard orgInfo={orgInfo.data} credits={credits.data} concurrency={concurrency.data} loading={credits.isLoading} />
        <div className="grid gap-6 lg:grid-cols-2">
          <ActiveCampaignsCard campaigns={dashboard.data?.active_campaigns} loading={dashboard.isLoading} />
          <RecentCallsCard
            calls={recentCalls.data}
            isLoading={recentCalls.isLoading}
            isError={recentCalls.isError}
            error={recentCalls.error}
            onRetry={() => recentCalls.refetch()}
          />
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="eyebrow">How you're trending</h2>
        <DashboardKpiRow kpis={dashboard.data?.kpis} trend={dashboard.data?.calls_last_7_days} loading={dashboard.isLoading} />
        <div className="grid gap-6 lg:grid-cols-3">
          <CallPerformanceCard data={dashboard.data?.calls_last_7_days} loading={dashboard.isLoading} className="lg:col-span-2" />
          <OutcomeBreakdownCard data={dashboard.data?.outcome_breakdown} loading={dashboard.isLoading} />
        </div>
      </section>
    </div>
  );
}
