import { IndianRupee, Phone, Zap } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { StatCard } from "@/components/shared/StatCard";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PlatformCallsChart, PlatformCreditsChart } from "@/components/charts/PlatformUsageCharts";
import { usePlatformUsageAnalytics } from "@/lib/platformHooks";

function formatPrice(priceMinor: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(priceMinor / 100);
}

export default function PlatformAnalytics() {
  const usage = usePlatformUsageAnalytics();

  const totalCalls30d = usage.data?.series.reduce((sum, p) => sum + p.calls, 0);
  const totalCredits30d = usage.data?.series.reduce((sum, p) => sum + p.credits, 0);

  return (
    <div className="space-y-6">
      <PageHeader title="Analytics" description="Platform-wide usage over the last 30 days." />

      {usage.isError ? (
        <ErrorBanner error={usage.error} onRetry={() => usage.refetch()} />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard
              icon={IndianRupee}
              label="Current MRR"
              value={usage.data ? formatPrice(usage.data.mrr_minor, usage.data.currency) : undefined}
              loading={usage.isLoading}
              tone="success"
            />
            <StatCard
              icon={Phone}
              label="Calls (last 30 days)"
              value={totalCalls30d?.toLocaleString()}
              loading={usage.isLoading}
              tone="info"
            />
            <StatCard
              icon={Zap}
              label="Credits used (last 30 days)"
              value={totalCredits30d?.toLocaleString()}
              loading={usage.isLoading}
              tone="warning"
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Calls per day</CardTitle>
              <CardDescription>Every call placed across all organizations, last 30 days.</CardDescription>
            </CardHeader>
            <CardContent className="pt-0">
              {usage.isLoading || !usage.data ? (
                <Skeleton className="h-60 w-full" />
              ) : (
                <PlatformCallsChart data={usage.data.series} />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Credits used per day</CardTitle>
              <CardDescription>
                1 credit = 1 billed call-minute (rounded up), counted only for calls that connected.
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-0">
              {usage.isLoading || !usage.data ? (
                <Skeleton className="h-60 w-full" />
              ) : (
                <PlatformCreditsChart data={usage.data.series} />
              )}
            </CardContent>
          </Card>

          <p className="text-xs text-muted-foreground">
            Revenue-over-time isn't shown here — there's no subscription-history or payment-ledger table yet, so a
            genuine trend line can't be computed without fabricating numbers. MRR above is a live snapshot instead.
          </p>
        </>
      )}
    </div>
  );
}
