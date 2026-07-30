import { Link } from "react-router-dom";
import { Megaphone } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { CampaignStatusBadge } from "@/components/shared/StatusBadge";
import type { Campaign } from "@/lib/types";

interface CampaignComparisonTableProps {
  campaigns: Campaign[] | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  onRetry: () => void;
}

export function CampaignComparisonTable({ campaigns, isLoading, isError, error, onRetry }: CampaignComparisonTableProps) {
  const ranked = (campaigns ?? [])
    .filter((c) => c.total_contacts > 0)
    .slice()
    .sort((a, b) => b.interested_count - a.interested_count)
    .slice(0, 8);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Campaign comparison</CardTitle>
        <p className="text-sm text-muted-foreground">Ranked by interested leads · Top 8</p>
      </CardHeader>
      <CardContent className="pt-0">
        {isError ? (
          <ErrorBanner error={error} onRetry={onRetry} />
        ) : isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : ranked.length === 0 ? (
          <EmptyState icon={Megaphone} title="No campaign data yet" description="Comparisons will appear once campaigns start dialing." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Campaign</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Completed</TableHead>
                <TableHead className="text-right">Interested</TableHead>
                <TableHead className="text-right">Conversion</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ranked.map((c) => {
                const conversion = c.completed_calls > 0 ? Math.round((c.interested_count / c.completed_calls) * 100) : 0;
                return (
                  <TableRow key={c.id}>
                    <TableCell>
                      <Link to={`/campaigns/${c.id}`} className="font-medium hover:text-primary hover:underline">
                        {c.name}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <CampaignStatusBadge status={c.status} />
                    </TableCell>
                    <TableCell className="text-right tabular-figure text-muted-foreground">
                      {c.completed_calls} / {c.total_contacts}
                    </TableCell>
                    <TableCell className="text-right tabular-figure font-medium text-success">{c.interested_count}</TableCell>
                    <TableCell className="text-right tabular-figure text-muted-foreground">{conversion}%</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
