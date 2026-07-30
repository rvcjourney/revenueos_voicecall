import { useMemo, useState } from "react";
import { CheckCircle2, ClipboardList, PlayCircle, Search, ShieldCheck } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { useActivity } from "@/lib/hooks";
import { formatDate, formatRelativeTime, titleCase } from "@/lib/utils";

const FILTERS = [
  { value: "all", label: "All Events" },
  { value: "campaign", label: "Campaigns" },
  { value: "agent", label: "Agent Access" },
];

const EVENT_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  campaign_created: ClipboardList,
  campaign_launched: PlayCircle,
  campaign_completed: CheckCircle2,
  agent_access_approved: ShieldCheck,
};

export default function AdminAudit() {
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const activity = useActivity();

  const filtered = useMemo(() => {
    let list = activity.data ?? [];
    if (filter === "campaign") list = list.filter((e) => e.type.includes("campaign"));
    if (filter === "agent") list = list.filter((e) => e.type.includes("agent"));
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(
        (e) => e.user_name.toLowerCase().includes(q) || e.detail.toLowerCase().includes(q) || e.agent_name?.toLowerCase().includes(q)
      );
    }
    return list;
  }, [activity.data, filter, search]);

  return (
    <div className="space-y-6">
      <PageHeader title="Audit Log" description="All platform activity for your organisation — last 60 events." />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Tabs value={filter} onValueChange={setFilter}>
          <TabsList>
            {FILTERS.map((f) => <TabsTrigger key={f.value} value={f.value}>{f.label}</TabsTrigger>)}
          </TabsList>
        </Tabs>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Search user, campaign..." value={search} onChange={(e) => setSearch(e.target.value)} className="w-full pl-8 sm:w-64" />
        </div>
      </div>

      {activity.isError ? (
        <ErrorBanner error={activity.error} onRetry={() => activity.refetch()} />
      ) : activity.isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : filtered.length > 0 ? (
        <Card>
          <CardContent className="divide-y divide-border/60 pt-6">
            {filtered.map((e, i) => {
              const Icon = EVENT_ICON[e.type] ?? ClipboardList;
              return (
                <div key={i} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
                    <Icon className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm">
                      <span className="font-medium">{titleCase(e.type)}</span>
                      <span className="text-muted-foreground"> by {e.user_name}</span>
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {e.detail}
                      {e.agent_name && ` · ${e.agent_name}`}
                      {e.campaign_status && ` · (${e.campaign_status})`}
                    </p>
                  </div>
                  <p className="shrink-0 whitespace-nowrap text-right text-xs text-muted-foreground" title={formatDate(e.timestamp)}>
                    {formatRelativeTime(e.timestamp)}
                  </p>
                </div>
              );
            })}
          </CardContent>
        </Card>
      ) : (
        <EmptyState icon={ClipboardList} title="No activity yet" description="Campaign and agent access events will appear here." />
      )}
    </div>
  );
}
