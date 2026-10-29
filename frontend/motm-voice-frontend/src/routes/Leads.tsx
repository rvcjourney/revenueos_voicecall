import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CalendarCheck, Download, Filter, KanbanSquare, Loader2, Mail, Plus, Search, Table2, Upload, UserRound, Users, X } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { CallOutcomeBadge } from "@/components/shared/StatusBadge";
import { DateRangePicker, KpiCards, PipelineFunnel, rangeParams, type DateRange, type KpiFilter } from "@/components/leads/LeadsOverview";
import { LeadsBulkBar } from "@/components/leads/LeadsBulkBar";
import { LeadsBoard } from "@/components/leads/LeadsBoard";
import { FollowUpText, PriorityBadge, followUpState, fromDateInput, toDateInput } from "@/components/leads/leadBits";
import { useLeads, useLeadsMeta, useUpdateLead } from "@/lib/hooks";
import { leadsApi, apiErrorMessage } from "@/lib/api";
import {
  LEAD_STATUSES, type Lead, type LeadEmailStatus, type LeadFilters, type LeadFollowUp, type LeadMeetingStatus,
  type LeadPriority, type LeadStatus,
} from "@/lib/types";
import { cn, formatDateTime, titleCase } from "@/lib/utils";

const PAGE_SIZES = [25, 50, 100];
const ANY = "all";
const pick = <T extends string>(v: string) => (v === ANY ? undefined : (v as T));

export default function Leads() {
  const [view, setView] = useState<"table" | "board">("table");
  const [range, setRange] = useState<DateRange>({ preset: "all", from: "", to: "" });
  const [status, setStatus] = useState<LeadStatus | undefined>();
  const [owner, setOwner] = useState(ANY);
  const [emailStatus, setEmailStatus] = useState(ANY);
  const [meetingStatus, setMeetingStatus] = useState(ANY);
  const [priority, setPriority] = useState(ANY);
  const [campaignId, setCampaignId] = useState(ANY);
  const [followUp, setFollowUp] = useState(ANY);
  // ?q= lets other pages (e.g. a call's "Open lead") land on a pre-filtered list.
  const [search, setSearch] = useState(() => new URLSearchParams(window.location.search).get("q") ?? "");
  const [pageSize, setPageSize] = useState(50);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [addOpen, setAddOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();

  const filters: LeadFilters = {
    status,
    owner: pick(owner),
    q: search.trim() || undefined,
    email_status: pick<LeadEmailStatus>(emailStatus),
    meeting_status: pick<LeadMeetingStatus>(meetingStatus),
    priority: pick<LeadPriority>(priority),
    campaign_id: pick(campaignId),
    follow_up: pick<LeadFollowUp>(followUp),
    ...rangeParams(range),
  };
  const leads = useLeads({ ...filters, limit: pageSize, offset });
  const meta = useLeadsMeta();
  const updateLead = useUpdateLead();

  const items = leads.data?.items ?? [];
  const total = leads.data?.total ?? 0;
  const hasFilters = [owner, emailStatus, meetingStatus, priority, campaignId, followUp].some((v) => v !== ANY)
    || !!search.trim() || !!status;

  // Any filter change goes back to the first page and drops the selection.
  function withReset<T>(set: (v: T) => void) {
    return (v: T) => { set(v); setOffset(0); setSelected(new Set()); };
  }

  function clearFilters() {
    setStatus(undefined); setOwner(ANY); setEmailStatus(ANY); setMeetingStatus(ANY);
    setPriority(ANY); setCampaignId(ANY); setFollowUp(ANY); setSearch(""); setOffset(0); setSelected(new Set());
  }

  function pickKpi(f: KpiFilter) {
    clearFilters();
    if (f === "all") return;
    if (f.status) setStatus(f.status);
    if (f.priority) setPriority(f.priority);
    if (f.follow_up) setFollowUp(f.follow_up);
  }

  async function save(id: string, data: Partial<Lead>, what: string) {
    try {
      await updateLead.mutateAsync({ id, data });
    } catch (err) {
      toast.error(apiErrorMessage(err, `Couldn't update ${what}`));
    }
  }

  async function handleImport(file: File | undefined) {
    if (!file) return;
    setImporting(true);
    try {
      const { data } = await leadsApi.importFile(file);
      toast.success(`Imported: ${data.created} new, ${data.updated} updated`);
      qc.invalidateQueries({ queryKey: ["leads"] });
    } catch (err) {
      toast.error(apiErrorMessage(err, "Import failed"));
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleExport() {
    try {
      await leadsApi.exportCsv(filters);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Export failed");
    }
  }

  const allOnPage = items.length > 0 && items.every((l) => selected.has(l.id));
  function toggleAll() {
    setSelected(allOnPage ? new Set() : new Set(items.map((l) => l.id)));
  }
  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Leads"
        description="Everyone your agents have called: pipeline, follow-ups, notes and results"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <DateRangePicker value={range} onChange={withReset(setRange)} />
            <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={(e) => handleImport(e.target.files?.[0])} />
            <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={importing}>
              {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Import
            </Button>
            <Button variant="outline" size="sm" onClick={handleExport}>
              <Download className="h-4 w-4" /> Export
            </Button>
            <Button variant="gradient" size="sm" onClick={() => setAddOpen(true)}>
              <Plus className="h-4 w-4" /> Add lead
            </Button>
          </div>
        }
      />

      <KpiCards data={leads.data} onPick={pickKpi} />
      <PipelineFunnel counts={leads.data?.status_counts ?? {}} active={status} onPick={withReset(setStatus)} />

      <Card>
        <CardContent className="space-y-3 pt-5">
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <Filter className="h-3.5 w-3.5" /> Filters{status && <span className="normal-case text-primary"> · {titleCase(status)}</span>}
            </p>
            {hasFilters && (
              <button onClick={clearFilters} className="flex items-center gap-1 text-xs text-primary hover:underline">
                <X className="h-3 w-3" /> Clear
              </button>
            )}
          </div>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search name, phone, email or company..."
              value={search}
              onChange={(e) => withReset(setSearch)(e.target.value)}
              className="pl-8"
            />
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <FilterSelect label="Owner" value={owner} onChange={withReset(setOwner)} options={[
              ["me", "My leads"], ["none", "Unassigned"], ...(meta.data?.members.map((m) => [m.id, m.name] as [string, string]) ?? []),
            ]} />
            <FilterSelect label="Priority" value={priority} onChange={withReset(setPriority)} options={[["hot", "Hot"], ["warm", "Warm"], ["cold", "Cold"]]} />
            <FilterSelect label="Follow-up" value={followUp} onChange={withReset(setFollowUp)} options={[
              ["due_today", "Due today"], ["overdue", "Overdue"], ["upcoming", "Upcoming"],
            ]} />
            <FilterSelect label="Source campaign" value={campaignId} onChange={withReset(setCampaignId)}
              options={meta.data?.campaigns.map((c) => [c.id, c.name] as [string, string]) ?? []} />
            <FilterSelect label="Email" value={emailStatus} onChange={withReset(setEmailStatus)} options={[
              ["none", "No email yet"], ["captured", "Email captured"], ["sent", "Email sent"], ["failed", "Email failed"], ["replied", "Replied"],
            ]} />
            <FilterSelect label="Meeting" value={meetingStatus} onChange={withReset(setMeetingStatus)} options={[
              ["none", "No meeting"], ["scheduled", "Meeting scheduled"], ["done", "Meeting done"], ["cancelled", "Meeting cancelled"],
            ]} />
          </div>
        </CardContent>
      </Card>

      <Tabs value={view} onValueChange={(v) => { setView(v as "table" | "board"); setSelected(new Set()); }}>
        <TabsList>
          <TabsTrigger value="table"><Table2 className="mr-1.5 h-4 w-4" /> Table</TabsTrigger>
          <TabsTrigger value="board"><KanbanSquare className="mr-1.5 h-4 w-4" /> Board</TabsTrigger>
        </TabsList>
      </Tabs>

      {view === "board" ? (
        <LeadsBoard filters={filters} />
      ) : leads.isError ? (
        <ErrorBanner error={leads.error} onRetry={() => leads.refetch()} />
      ) : leads.isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Users}
          title={hasFilters ? "No leads match these filters" : "No leads here yet"}
          description="Leads appear automatically after campaign calls. You can also add one or import a CSV."
        />
      ) : (
        <div className="space-y-3">
          {selected.size > 0 && (
            <LeadsBulkBar ids={[...selected]} meta={meta.data} filters={filters} onDone={() => setSelected(new Set())} />
          )}
          <Card className="overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-5 py-3">
              <p className="text-sm font-semibold">{total} lead{total === 1 ? "" : "s"}</p>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>Rows</span>
                <Select value={String(pageSize)} onValueChange={(v) => { setPageSize(Number(v)); setOffset(0); setSelected(new Set()); }}>
                  <SelectTrigger className="h-8 w-20 text-xs" aria-label="Rows per page"><SelectValue /></SelectTrigger>
                  <SelectContent>{PAGE_SIZES.map((n) => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}</SelectContent>
                </Select>
                <span className="tabular-figure">{offset + 1}–{Math.min(offset + pageSize, total)} of {total}</span>
                <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset - pageSize)); setSelected(new Set()); }}>Prev</Button>
                <Button variant="outline" size="sm" disabled={offset + pageSize >= total} onClick={() => { setOffset(offset + pageSize); setSelected(new Set()); }}>Next</Button>
              </div>
            </div>
            {/* Own scroll box (not <Table>'s), so the header can stick while rows scroll. */}
            <div className="max-h-[70vh] overflow-auto">
              <table className="w-full caption-bottom text-sm">
                <TableHeader className="sticky top-0 z-10 bg-card shadow-[0_1px_0_hsl(var(--border))]">
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="w-10">
                      <Checkbox checked={allOnPage} onCheckedChange={toggleAll} aria-label="Select all on this page" />
                    </TableHead>
                    <TableHead>Lead</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Priority</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead>Last call</TableHead>
                    <TableHead>Next follow-up</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Meeting</TableHead>
                    <TableHead>Owner</TableHead>
                    <TableHead className="min-w-56">Note</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((l) => (
                    <TableRow key={l.id} data-state={selected.has(l.id) ? "selected" : undefined}>
                      <TableCell>
                        <Checkbox checked={selected.has(l.id)} onCheckedChange={() => toggle(l.id)} aria-label={`Select ${l.name || l.phone}`} />
                      </TableCell>
                      <TableCell className="min-w-44">
                        <Link to={`/leads/${l.id}`} className="block hover:underline">
                          <span className="font-medium">{l.name || "Unnamed"}</span>
                          {l.company && <span className="text-muted-foreground"> · {l.company}</span>}
                        </Link>
                        <span className="font-mono text-xs text-muted-foreground">{l.phone}</span>
                      </TableCell>
                      <TableCell>
                        <Select value={l.status} onValueChange={(v) => save(l.id, { status: v as LeadStatus }, "status")}>
                          <SelectTrigger className="h-8 w-36 text-xs" aria-label={`Status of ${l.name || l.phone}`}><SelectValue /></SelectTrigger>
                          <SelectContent>{LEAD_STATUSES.map((s) => <SelectItem key={s} value={s}>{titleCase(s)}</SelectItem>)}</SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell>
                        <Select value={l.priority ?? ""} onValueChange={(v) => save(l.id, { priority: v as LeadPriority }, "priority")}>
                          <SelectTrigger className="h-8 w-24 border-transparent px-1 text-xs" aria-label={`Priority of ${l.name || l.phone}`}>
                            {l.priority ? <PriorityBadge priority={l.priority} /> : <span className="text-muted-foreground">Set</span>}
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="hot">Hot</SelectItem>
                            <SelectItem value="warm">Warm</SelectItem>
                            <SelectItem value="cold">Cold</SelectItem>
                          </SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell className="text-xs">
                        {l.source === "campaign"
                          ? <span title="Campaign">{l.source_campaign_name ?? "Campaign"}</span>
                          : <span className="text-muted-foreground">{titleCase(l.source)}</span>}
                      </TableCell>
                      <TableCell className="min-w-56 max-w-xs">
                        {l.last_outcome ? (
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <CallOutcomeBadge outcome={l.last_outcome} />
                              <span className="text-xs text-muted-foreground">{formatDateTime(l.last_called_at)}</span>
                            </div>
                            {l.last_summary && <p className="line-clamp-2 text-xs text-muted-foreground">{l.last_summary}</p>}
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">Not called yet</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Input
                          type="date"
                          aria-label={`Next follow-up for ${l.name || l.phone}`}
                          value={toDateInput(l.next_follow_up_at)}
                          onChange={(e) => save(l.id, { next_follow_up_at: fromDateInput(e.target.value) }, "follow-up")}
                          className={cn(
                            "h-8 w-36 text-xs",
                            followUpState(l.next_follow_up_at) === "overdue" && "border-destructive text-destructive",
                            followUpState(l.next_follow_up_at) === "today" && "border-warning text-warning",
                          )}
                        />
                        {l.next_follow_up_at && <span className="mt-0.5 block text-[11px]"><FollowUpText at={l.next_follow_up_at} /></span>}
                      </TableCell>
                      <TableCell>
                        <span className={cn("flex items-center gap-1.5 text-xs", l.email_status === "sent" || l.email_status === "replied" ? "text-success" : l.email_status === "failed" ? "text-destructive" : "text-muted-foreground")}>
                          <Mail className="h-3.5 w-3.5" />
                          {l.email_status === "none" ? (l.email ? "Not sent" : "—") : titleCase(l.email_status)}
                        </span>
                      </TableCell>
                      <TableCell>
                        {l.meeting_status === "none" ? (
                          <span className="text-xs text-muted-foreground">—</span>
                        ) : (
                          <span className={cn("flex items-center gap-1.5 text-xs", l.meeting_status === "scheduled" ? "text-primary" : "text-muted-foreground")}>
                            <CalendarCheck className="h-3.5 w-3.5" />
                            {titleCase(l.meeting_status)}{l.meeting_at_text ? ` · ${l.meeting_at_text}` : ""}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {l.owner_name ? (
                          <span className="flex items-center gap-1.5 whitespace-nowrap"><UserRound className="h-3.5 w-3.5" />{l.owner_name}</span>
                        ) : "—"}
                      </TableCell>
                      <TableCell>
                        <RowNote lead={l} onSave={(note) => save(l.id, { note }, "note")} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </table>
            </div>
          </Card>
        </div>
      )}

      <AddLeadDialog open={addOpen} onOpenChange={setAddOpen} />
    </div>
  );
}

function FilterSelect({
  label, value, onChange, options,
}: { label: string; value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger aria-label={label} className={cn(value !== ANY && "border-primary/60")}>
        <SelectValue placeholder={label} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ANY}>Any {label.toLowerCase()}</SelectItem>
        {options.map(([v, text]) => <SelectItem key={v} value={v}>{text}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

/** The row's sticky note: type, then click away (or Enter) to save. */
function RowNote({ lead, onSave }: { lead: Lead; onSave: (note: string | null) => void }) {
  const [text, setText] = useState(lead.note ?? "");
  const [seen, setSeen] = useState(lead.note);
  if (seen !== lead.note) { // someone else saved a newer note; show it
    setSeen(lead.note);
    setText(lead.note ?? "");
  }
  const commit = () => { if (text.trim() !== (lead.note ?? "")) onSave(text.trim() || null); };
  return (
    <Input
      value={text}
      placeholder="Add a note…"
      aria-label={`Note for ${lead.name || lead.phone}`}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
      maxLength={5000}
      className="h-8 min-w-56 text-xs"
    />
  );
}

function AddLeadDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [form, setForm] = useState({ phone: "", name: "", email: "", company: "" });
  const [saving, setSaving] = useState(false);
  const qc = useQueryClient();

  async function save() {
    setSaving(true);
    try {
      await leadsApi.create({
        phone: form.phone,
        name: form.name || undefined,
        email: form.email || undefined,
        company: form.company || undefined,
      });
      toast.success("Lead added");
      qc.invalidateQueries({ queryKey: ["leads"] });
      setForm({ phone: "", name: "", email: "", company: "" });
      onOpenChange(false);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't add lead"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Add lead</DialogTitle></DialogHeader>
        <div className="space-y-3">
          {([
            ["phone", "Phone *", "+91 98765 43210"],
            ["name", "Name", ""],
            ["email", "Email", ""],
            ["company", "Company", ""],
          ] as const).map(([key, label, placeholder]) => (
            <div key={key} className="space-y-1.5">
              <Label htmlFor={`lead-${key}`}>{label}</Label>
              <Input
                id={`lead-${key}`}
                placeholder={placeholder}
                value={form[key]}
                onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              />
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="gradient" onClick={save} disabled={saving || !form.phone.trim()}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />} Add lead
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
