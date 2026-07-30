import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { CallVolumeChart } from "@/components/charts/CallVolumeChart";
import type { DashboardStats } from "@/lib/types";

interface CallPerformanceCardProps {
  data: DashboardStats["calls_last_7_days"] | undefined;
  loading?: boolean;
  className?: string;
}

export function CallPerformanceCard({ data, loading, className }: CallPerformanceCardProps) {
  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Call performance</CardTitle>
          <p className="text-sm text-muted-foreground">Total calls vs. interested leads · Last 7 days</p>
        </div>
        <Button variant="ghost" size="sm" asChild>
          <Link to="/analytics">
            Deeper analytics <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <Skeleton className="h-[280px] w-full" />
        ) : data && data.length > 0 ? (
          <CallVolumeChart data={data} />
        ) : (
          <EmptyState title="No call activity yet" description="Launch a campaign to start seeing performance data here." />
        )}
      </CardContent>
    </Card>
  );
}
