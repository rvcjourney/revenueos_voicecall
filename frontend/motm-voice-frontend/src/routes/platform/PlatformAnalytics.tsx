import { useEffect, useState } from "react";
import { toast } from "sonner";
import { IndianRupee, Loader2, Percent, Phone, TrendingUp, Wallet, Zap } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { StatCard } from "@/components/shared/StatCard";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { PlatformCallsChart, PlatformCreditsChart } from "@/components/charts/PlatformUsageCharts";
import { platformApiErrorMessage } from "@/lib/platformApi";
import {
  usePlatformCostSettings,
  usePlatformUsageAnalytics,
  useUpdatePlatformCostSettings,
} from "@/lib/platformHooks";

function formatPrice(priceMinor: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(priceMinor / 100);
}

export default function PlatformAnalytics() {
  const usage = usePlatformUsageAnalytics();

  const totalCalls30d = usage.data?.series.reduce((sum, p) => sum + p.calls, 0);
  const totalCredits30d = usage.data?.series.reduce((sum, p) => sum + p.credits, 0);
  const marginPositive = (usage.data?.estimated_gross_margin_minor ?? 0) >= 0;

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

          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard
              icon={Wallet}
              label="Avg. plan price / org"
              value={usage.data ? formatPrice(usage.data.average_plan_price_minor, usage.data.currency) : undefined}
              loading={usage.isLoading}
              tone="default"
            />
            <StatCard
              icon={TrendingUp}
              label="Est. gross margin (30d)"
              value={
                usage.data ? formatPrice(usage.data.estimated_gross_margin_minor, usage.data.currency) : undefined
              }
              loading={usage.isLoading}
              tone={marginPositive ? "success" : "warning"}
            />
            <StatCard
              icon={Percent}
              label="Est. margin %"
              value={usage.data ? `${usage.data.estimated_margin_percent.toFixed(1)}%` : undefined}
              loading={usage.isLoading}
              tone={marginPositive ? "success" : "warning"}
            />
          </div>

          <CostRateCard costPerMinuteMinor={usage.data?.cost_per_minute_minor} currency={usage.data?.currency} />

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
            Gross margin and margin % are estimates: 30-day real call-minutes multiplied by the ₹/minute cost rate
            below, compared against the current MRR snapshot — not a precise per-org P&L.
          </p>
        </>
      )}
    </div>
  );
}

function CostRateCard({ costPerMinuteMinor, currency }: { costPerMinuteMinor?: number; currency?: string }) {
  const costSettings = usePlatformCostSettings();
  const updateCostSettings = useUpdatePlatformCostSettings();
  const [rate, setRate] = useState("");

  useEffect(() => {
    if (costSettings.data) setRate(String(costSettings.data.cost_per_minute_minor));
  }, [costSettings.data]);

  async function save() {
    const value = Number(rate);
    if (!Number.isFinite(value) || value < 0) {
      toast.error("Enter a valid, non-negative cost per minute");
      return;
    }
    try {
      await updateCostSettings.mutateAsync({ cost_per_minute_minor: value });
      toast.success("Cost rate updated");
    } catch (err) {
      toast.error(platformApiErrorMessage(err, "Couldn't update cost rate"));
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 pt-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1.5">
          <Label>Blended cost per call-minute (minor units{currency ? `, ${currency}` : ""})</Label>
          <p className="text-xs text-muted-foreground">
            One estimate covering Groq + ElevenLabs + Vobiz + LiveKit combined, used to compute estimated gross
            margin above. Current: {costPerMinuteMinor != null && currency ? formatPrice(costPerMinuteMinor, currency) : "—"}/min.
          </p>
          <Input
            type="number"
            min={0}
            className="max-w-40"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            disabled={costSettings.isLoading}
          />
        </div>
        <Button variant="gradient" size="sm" onClick={save} disabled={updateCostSettings.isPending || costSettings.isLoading}>
          {updateCostSettings.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          Save
        </Button>
      </CardContent>
    </Card>
  );
}
