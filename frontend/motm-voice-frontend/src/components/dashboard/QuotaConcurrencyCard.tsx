import { Gauge, PhoneCall } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import type { ConcurrencyUsage, CreditUsage, OrgQuotaInfo } from "@/lib/types";

interface QuotaConcurrencyCardProps {
  orgInfo: OrgQuotaInfo | undefined;
  credits: CreditUsage | undefined;
  concurrency: ConcurrencyUsage | undefined;
  loading?: boolean;
}

export function QuotaConcurrencyCard({ orgInfo, credits, concurrency, loading }: QuotaConcurrencyCardProps) {
  const creditsPct = credits ? Math.min((credits.used / Math.max(credits.allotted, 1)) * 100, 100) : 0;
  const creditsNear = creditsPct >= 85;
  const concurrencyPct = concurrency ? Math.min((concurrency.in_use / Math.max(concurrency.max, 1)) * 100, 100) : 0;

  return (
    <Card className="card-top-accent">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Gauge className="h-4 w-4 text-primary" /> Capacity right now
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-6 pt-0 sm:grid-cols-2">
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <p className="font-medium">
              Credits used
              {orgInfo && <span className="ml-2 text-xs capitalize text-muted-foreground">· {orgInfo.plan_tier} plan</span>}
            </p>
            {credits && (
              <p className="text-muted-foreground">
                {credits.used.toLocaleString()} / {credits.allotted.toLocaleString()}
              </p>
            )}
          </div>
          {loading || !credits ? <Skeleton className="h-2 w-full" /> : <Progress value={creditsPct} />}
          {creditsNear && <p className="text-xs text-warning">Approaching credit limit — {Math.round(creditsPct)}% used</p>}
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <p className="flex items-center gap-1.5 font-medium">
              <PhoneCall className="h-3.5 w-3.5 text-muted-foreground" /> Concurrent lines
            </p>
            {concurrency && (
              <p className="text-muted-foreground">
                {concurrency.in_use} / {concurrency.max}
              </p>
            )}
          </div>
          {loading || !concurrency ? (
            <Skeleton className="h-2 w-full" />
          ) : (
            <Progress value={concurrencyPct} />
          )}
          {concurrency && concurrency.queued > 0 && (
            <p className="text-xs text-info">{concurrency.queued} call{concurrency.queued === 1 ? "" : "s"} queued, waiting for a free line</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
