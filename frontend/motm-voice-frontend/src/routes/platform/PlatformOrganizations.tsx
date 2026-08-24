import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/shared/PageHeader";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { EmptyState } from "@/components/shared/EmptyState";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePlatformOrgs } from "@/lib/platformHooks";
import { formatDate } from "@/lib/utils";

const PAGE_SIZE = 50;

export default function PlatformOrganizations() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    setOffset(0);
  }, [debouncedSearch]);

  const orgs = usePlatformOrgs({ q: debouncedSearch || undefined, limit: PAGE_SIZE, offset });

  // Backend returns a plain array (no {items, total} envelope) — paginate off
  // what's actually on this page rather than a total the API never provides.
  const items = orgs.data ?? [];
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const hasNextPage = items.length === PAGE_SIZE;

  return (
    <div className="space-y-6">
      <PageHeader title="Organizations" description="Every tenant on the platform." />

      <div className="relative max-w-sm">
        <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search by name or slug..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-8"
        />
      </div>

      {orgs.isError ? (
        <ErrorBanner error={orgs.error} onRetry={() => orgs.refetch()} />
      ) : orgs.isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : items.length === 0 ? (
        <EmptyState title="No organizations found" description="Try a different search term." />
      ) : (
        <>
          <Card className="overflow-hidden py-0">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="pl-5">Organization</TableHead>
                  <TableHead>Plan</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Usage (min)</TableHead>
                  <TableHead className="pr-5">Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((org) => {
                  const ratio = org.credits_per_month > 0 ? Math.min(100, (org.credits_used_this_period / org.credits_per_month) * 100) : 0;
                  return (
                    <TableRow
                      key={org.id}
                      className="cursor-pointer"
                      onClick={() => navigate(`/ops/organizations/${org.id}`)}
                    >
                      <TableCell className="pl-5">
                        <p className="text-sm font-medium">{org.name}</p>
                        <p className="text-xs text-muted-foreground">{org.slug}</p>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary" className="capitalize">
                          {org.plan_name}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={org.is_active ? "success" : "muted"}>
                          {org.is_active ? "Active" : "Suspended"}
                        </Badge>
                      </TableCell>
                      <TableCell className="min-w-40">
                        <div className="flex items-center gap-2">
                          <Progress value={ratio} className="h-1.5 w-24" />
                          <span className="whitespace-nowrap text-xs text-muted-foreground">
                            {org.credits_used_this_period.toLocaleString()} / {org.credits_per_month.toLocaleString()}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="pr-5 text-xs text-muted-foreground">{formatDate(org.created_at)}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </Card>

          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>Page {page} · {items.length} organization{items.length === 1 ? "" : "s"}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))} disabled={offset === 0}>
                <ChevronLeft className="h-3.5 w-3.5" /> Previous
              </Button>
              <Button variant="outline" size="sm" onClick={() => setOffset((o) => o + PAGE_SIZE)} disabled={!hasNextPage}>
                Next <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
