import { Link } from "react-router-dom";
import { ArrowRight, Megaphone } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { CampaignStatusBadge } from "@/components/shared/StatusBadge";
import type { DashboardStats } from "@/lib/types";

interface ActiveCampaignsCardProps {
  campaigns: DashboardStats["active_campaigns"] | undefined;
  loading?: boolean;
}

export function ActiveCampaignsCard({ campaigns, loading }: ActiveCampaignsCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-base">
          <Megaphone className="h-4 w-4 text-primary" /> Active campaigns
        </CardTitle>
        <Button variant="ghost" size="sm" asChild>
          <Link to="/campaigns">
            View all <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : campaigns && campaigns.length > 0 ? (
          <div className="space-y-3">
            {campaigns.map((c) => {
              const pct = c.total_contacts > 0 ? Math.round((c.completed_calls / c.total_contacts) * 100) : 0;
              return (
                <Link
                  key={c.id}
                  to={`/campaigns/${c.id}`}
                  className="block rounded-lg border border-border p-3 transition-colors hover:border-primary/40 hover:bg-accent/40"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2.5">
                      <CampaignStatusBadge status={c.status} />
                      <p className="truncate text-sm font-medium">{c.name}</p>
                    </div>
                    <div className="flex shrink-0 gap-4 text-xs text-muted-foreground">
                      <span>
                        {c.completed_calls} / {c.total_contacts}
                      </span>
                      <span className="text-success">{c.interested_count} interested</span>
                    </div>
                  </div>
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-[image:var(--gradient-primary)]" style={{ width: `${pct}%` }} />
                  </div>
                </Link>
              );
            })}
          </div>
        ) : (
          <EmptyState
            title="No active campaigns"
            description="Create your first campaign to start calling leads with an AI voice agent."
            action={
              <Button variant="gradient" asChild>
                <Link to="/campaigns/new">New campaign</Link>
              </Button>
            }
          />
        )}
      </CardContent>
    </Card>
  );
}
