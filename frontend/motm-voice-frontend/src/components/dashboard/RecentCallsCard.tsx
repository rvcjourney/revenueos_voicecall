import { Link } from "react-router-dom";
import { ArrowRight, Phone } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { CallOutcomeBadge } from "@/components/shared/StatusBadge";
import type { Call } from "@/lib/types";
import { callDurationSeconds, formatDateTime, formatDuration } from "@/lib/utils";

interface RecentCallsCardProps {
  calls: Call[] | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  onRetry: () => void;
}

export function RecentCallsCard({ calls, isLoading, isError, error, onRetry }: RecentCallsCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-base">
          <Phone className="h-4 w-4 text-primary" /> Recent calls
        </CardTitle>
        <Button variant="ghost" size="sm" asChild>
          <Link to="/calls">
            View all <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </CardHeader>
      <CardContent className="pt-0">
        {isError ? (
          <ErrorBanner error={error} onRetry={onRetry} />
        ) : isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : calls && calls.length > 0 ? (
          <div className="space-y-3">
            {calls.map((c) => (
              <Link
                key={c.id}
                to={`/calls/${c.id}`}
                className="flex flex-col gap-2 rounded-lg border border-border p-3 transition-colors hover:border-primary/40 hover:bg-accent/40 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/12 text-primary">
                    <Phone className="h-4 w-4" />
                  </span>
                  <div>
                    <p className="font-mono text-sm">{c.phone_number}</p>
                    <p className="text-xs text-muted-foreground">{formatDateTime(c.started_at)}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span>{formatDuration(callDurationSeconds(c))}</span>
                  <CallOutcomeBadge outcome={c.outcome} />
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState icon={Phone} title="No calls yet" description="Calls will show up here as your campaigns start dialing." />
        )}
      </CardContent>
    </Card>
  );
}
