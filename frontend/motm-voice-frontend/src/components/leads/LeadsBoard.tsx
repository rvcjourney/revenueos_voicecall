import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { CalendarClock, UserRound } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { useLeads, useUpdateLead } from "@/lib/hooks";
import { apiErrorMessage } from "@/lib/api";
import { LEAD_STATUSES, type Lead, type LeadFilters, type LeadStatus } from "@/lib/types";
import { cn, formatDate, titleCase } from "@/lib/utils";
import { FollowUpText, PriorityBadge } from "./leadBits";

// shortcut: the board loads the first 200 leads matching the filters; narrow the filters (or use the table) beyond that.
const BOARD_LIMIT = 200;

/** Pipeline board: one column per stage, drag a card to move the lead. */
export function LeadsBoard({ filters }: { filters: LeadFilters }) {
  const leads = useLeads({ ...filters, status: undefined, limit: BOARD_LIMIT, offset: 0 });
  const update = useUpdateLead();
  const [over, setOver] = useState<LeadStatus | null>(null);

  if (leads.isError) return <ErrorBanner error={leads.error} onRetry={() => leads.refetch()} />;
  if (leads.isLoading) return <Skeleton className="h-96 w-full" />;

  const items = leads.data?.items ?? [];
  const byStatus = (s: LeadStatus) => items.filter((l) => l.status === s);

  async function move(id: string, to: LeadStatus) {
    const lead = items.find((l) => l.id === id);
    if (!lead || lead.status === to) return;
    try {
      await update.mutateAsync({ id, data: { status: to } });
      toast.success(`${lead.name || lead.phone} → ${titleCase(to)}`);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't move the lead"));
    }
  }

  return (
    <div className="space-y-2">
      {(leads.data?.total ?? 0) > BOARD_LIMIT && (
        <p className="text-xs text-muted-foreground">Showing the first {BOARD_LIMIT} of {leads.data?.total} leads. Narrow the filters to see the rest.</p>
      )}
      <div className="flex gap-3 overflow-x-auto pb-2">
        {LEAD_STATUSES.map((s) => {
          const col = byStatus(s);
          return (
            <section
              key={s}
              aria-label={titleCase(s)}
              onDragOver={(e) => { e.preventDefault(); setOver(s); }}
              onDragLeave={() => setOver((o) => (o === s ? null : o))}
              onDrop={(e) => { e.preventDefault(); setOver(null); move(e.dataTransfer.getData("text/plain"), s); }}
              className={cn(
                "flex w-64 shrink-0 flex-col rounded-lg border border-border bg-muted/30",
                over === s && "border-primary bg-primary/5"
              )}
            >
              <header className="flex items-center justify-between border-b border-border px-3 py-2">
                <span className="text-xs font-semibold">{titleCase(s)}</span>
                <span className="tabular-figure rounded-full bg-background px-2 text-xs text-muted-foreground">{col.length}</span>
              </header>
              <div className="flex max-h-[65vh] min-h-24 flex-col gap-2 overflow-y-auto p-2">
                {col.map((l) => <BoardCard key={l.id} lead={l} />)}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

function BoardCard({ lead }: { lead: Lead }) {
  return (
    <article
      draggable
      onDragStart={(e) => { e.dataTransfer.setData("text/plain", lead.id); e.dataTransfer.effectAllowed = "move"; }}
      className="cursor-grab space-y-1.5 rounded-md border border-border bg-card p-2.5 text-xs shadow-sm active:cursor-grabbing"
    >
      <div className="flex items-start justify-between gap-2">
        <Link to={`/leads/${lead.id}`} className="font-medium hover:underline">{lead.name || lead.phone}</Link>
        <PriorityBadge priority={lead.priority} />
      </div>
      {lead.company && <p className="text-muted-foreground">{lead.company}</p>}
      {lead.next_follow_up_at && (
        <p className="flex items-center gap-1"><CalendarClock className="h-3 w-3" /><FollowUpText at={lead.next_follow_up_at} /></p>
      )}
      <div className="flex items-center justify-between text-muted-foreground">
        <span className="flex items-center gap-1"><UserRound className="h-3 w-3" />{lead.owner_name ?? "Unassigned"}</span>
        {lead.last_called_at && <span>{formatDate(lead.last_called_at)}</span>}
      </div>
    </article>
  );
}
