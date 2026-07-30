import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { OutcomeDonutChart } from "@/components/charts/OutcomeDonutChart";
import type { DashboardStats } from "@/lib/types";

interface OutcomeBreakdownCardProps {
  data: DashboardStats["outcome_breakdown"] | undefined;
  loading?: boolean;
  detailed?: boolean;
}

export function OutcomeBreakdownCard({ data, loading, detailed }: OutcomeBreakdownCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Outcome breakdown</CardTitle>
        <p className="text-sm text-muted-foreground">Last 30 days</p>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <Skeleton className="h-[280px] w-full" />
        ) : data && data.some((o) => o.value > 0) ? (
          <OutcomeDonutChart data={data} detailed={detailed} />
        ) : (
          <EmptyState title="No outcomes yet" description="Outcome tags will appear as calls complete." />
        )}
      </CardContent>
    </Card>
  );
}
