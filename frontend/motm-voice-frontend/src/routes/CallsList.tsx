import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Clock, Filter, Heart, Phone, Search, X } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { CallOutcomeBadge } from "@/components/shared/StatusBadge";
import { useCalls, useCampaigns } from "@/lib/hooks";
import { callDurationSeconds, formatDateTime, formatDuration } from "@/lib/utils";

const OUTCOMES = [
  "interested",
  "not_interested",
  "callback_requested",
  "wrong_number",
  "do_not_call",
  "voicemail",
  "no_answer",
  "pending",
];

export default function CallsList() {
  const [campaignId, setCampaignId] = useState("all");
  const [outcome, setOutcome] = useState("all");
  const [search, setSearch] = useState("");

  const campaigns = useCampaigns();
  const calls = useCalls({
    campaign_id: campaignId === "all" ? undefined : campaignId,
    outcome: outcome === "all" ? undefined : outcome,
    limit: 200,
  });

  const campaignNameById = useMemo(() => {
    const map = new Map<string, string>();
    campaigns.data?.forEach((c) => map.set(c.id, c.name));
    return map;
  }, [campaigns.data]);

  const filtered = useMemo(() => {
    if (!search.trim()) return calls.data ?? [];
    const q = search.trim();
    return (calls.data ?? []).filter((c) => c.phone_number.includes(q));
  }, [calls.data, search]);

  const stats = useMemo(() => {
    const list = calls.data ?? [];
    const interested = list.filter((c) => c.outcome === "interested").length;
    const withDuration = list.filter((c) => (callDurationSeconds(c) ?? 0) > 0);
    const avgDuration = withDuration.length
      ? Math.round(withDuration.reduce((sum, c) => sum + (callDurationSeconds(c) ?? 0), 0) / withDuration.length)
      : 0;
    return { total: list.length, interested, avgDuration };
  }, [calls.data]);

  const hasFilters = campaignId !== "all" || outcome !== "all" || search.trim().length > 0;

  function clearFilters() {
    setCampaignId("all");
    setOutcome("all");
    setSearch("");
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Call History" description={`${calls.data?.length ?? 0} total calls`} />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard icon={Phone} label="Total calls" value={stats.total} loading={calls.isLoading} />
        <StatCard icon={Heart} label="Interested" value={stats.interested} loading={calls.isLoading} tone="success" />
        <StatCard
          icon={Clock}
          label="Avg. duration"
          value={calls.isLoading ? undefined : formatDuration(stats.avgDuration)}
          loading={calls.isLoading}
          tone="info"
        />
      </div>

      <Card>
        <CardContent className="space-y-3 pt-5">
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <Filter className="h-3.5 w-3.5" /> Filters
            </p>
            {hasFilters && (
              <button onClick={clearFilters} className="flex items-center gap-1 text-xs text-primary hover:underline">
                <X className="h-3 w-3" /> Clear
              </button>
            )}
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Select value={campaignId} onValueChange={setCampaignId}>
              <SelectTrigger className="sm:w-56"><SelectValue placeholder="All Campaigns" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Campaigns</SelectItem>
                {campaigns.data?.map((c) => (
                  <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={outcome} onValueChange={setOutcome}>
              <SelectTrigger className="sm:w-56"><SelectValue placeholder="All Outcomes" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Outcomes</SelectItem>
                {OUTCOMES.map((o) => (
                  <SelectItem key={o} value={o} className="capitalize">{o.replace("_", " ")}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder="Search by phone..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-8" />
            </div>
          </div>
        </CardContent>
      </Card>

      {calls.isError ? (
        <ErrorBanner error={calls.error} onRetry={() => calls.refetch()} />
      ) : calls.isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : filtered.length === 0 ? (
        <EmptyState icon={Phone} title="No calls found" description="Try adjusting your filters, or launch a campaign to start dialing." />
      ) : (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <p className="text-sm font-semibold">All calls</p>
            <p className="text-xs text-muted-foreground">
              Showing {filtered.length} of {calls.data?.length ?? 0}
            </p>
          </div>
          <CardContent className="overflow-x-auto p-0">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Phone</TableHead>
                  <TableHead>Campaign</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Outcome</TableHead>
                  <TableHead>Cost</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell>
                      <div className="flex items-center gap-2.5">
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/12 text-primary">
                          <Phone className="h-3.5 w-3.5" />
                        </span>
                        <span className="font-mono text-xs">{c.phone_number}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {c.campaign_id ? campaignNameById.get(c.campaign_id) ?? "—" : "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{formatDateTime(c.started_at)}</TableCell>
                    <TableCell className="tabular-figure text-sm">{formatDuration(callDurationSeconds(c))}</TableCell>
                    <TableCell><CallOutcomeBadge outcome={c.outcome} /></TableCell>
                    <TableCell className="tabular-figure text-sm">{c.cost_inr != null ? `₹${c.cost_inr.toFixed(2)}` : "—"}</TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" asChild>
                        <Link to={`/calls/${c.id}`}>
                          <Phone className="h-3.5 w-3.5" /> View
                        </Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
