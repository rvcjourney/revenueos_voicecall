import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CalendarCheck, Download, Filter, Loader2, Mail, Plus, Search, Upload, UserRound, Users, X } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { CallOutcomeBadge } from "@/components/shared/StatusBadge";
import { useLeads, useLeadsMeta, useUpdateLead } from "@/lib/hooks";
import { leadsApi, apiErrorMessage } from "@/lib/api";
import { LEAD_STATUSES, type LeadEmailStatus, type LeadFilters, type LeadMeetingStatus, type LeadStatus } from "@/lib/types";
import { cn, formatDateTime, titleCase } from "@/lib/utils";

const PAGE = 50;

export default function Leads() {
  const [status, setStatus] = useState<LeadStatus | "all">("all");
  const [owner, setOwner] = useState("all");
  const [emailStatus, setEmailStatus] = useState<LeadEmailStatus | "all">("all");
  const [meetingStatus, setMeetingStatus] = useState<LeadMeetingStatus | "all">("all");
  // ?q= lets other pages (e.g. a call's "Open lead") land on a pre-filtered list.
  const [search, setSearch] = useState(() => new URLSearchParams(window.location.search).get("q") ?? "");
  const [offset, setOffset] = useState(0);
  const [addOpen, setAddOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();

  const filters: LeadFilters = {
    status: status === "all" ? undefined : status,
    owner: owner === "all" ? undefined : owner,
    q: search.trim() || undefined,
    email_status: emailStatus === "all" ? undefined : emailStatus,
    meeting_status: meetingStatus === "all" ? undefined : meetingStatus,
  };
  const leads = useLeads({ ...filters, limit: PAGE, offset });
  const meta = useLeadsMeta();
  const updateLead = useUpdateLead();

  const items = leads.data?.items ?? [];
  const total = leads.data?.total ?? 0;
  const counts = leads.data?.status_counts ?? {};
  const allCount = Object.values(counts).reduce((a, b) => a + (b ?? 0), 0);
  const hasFilters = owner !== "all" || emailStatus !== "all" || meetingStatus !== "all" || !!search.trim();

  // Any filter change goes back to the first page.
  function withReset<T>(set: (v: T) => void) {
    return (v: T) => { set(v); setOffset(0); };
  }

  function clearFilters() {
    setOwner("all"); setEmailStatus("all"); setMeetingStatus("all"); setSearch(""); setOffset(0);
  }

  async function changeStatus(id: string, next: LeadStatus) {
    try {
      await updateLead.mutateAsync({ id, data: { status: next } });
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't update status"));
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

  return (
    <div className="space-y-6">
      <PageHeader
        title="Leads"
        description="Everyone your agents have called, with results, follow-ups and notes"
        actions={
          <div className="flex flex-wrap gap-2">
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

      <div className="flex flex-wrap gap-2">
        {(["all", ...LEAD_STATUSES] as const).map((s) => (
          <button
            key={s}
            onClick={() => withReset(setStatus)(s)}
            className={cn(
              "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
              status === s ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:text-foreground"
            )}
          >
            {s === "all" ? "All" : titleCase(s)}{" "}
            <span className="tabular-figure opacity-70">{s === "all" ? allCount : counts[s] ?? 0}</span>
          </button>
        ))}
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
          <div className="flex flex-col gap-3 lg:flex-row">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search name, phone, email or company..."
                value={search}
                onChange={(e) => withReset(setSearch)(e.target.value)}
                className="pl-8"
              />
            </div>
            <Select value={owner} onValueChange={withReset(setOwner)}>
              <SelectTrigger className="lg:w-48"><SelectValue placeholder="Any owner" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any owner</SelectItem>
                <SelectItem value="me">My leads</SelectItem>
                <SelectItem value="none">Unassigned</SelectItem>
                {meta.data?.members.map((m) => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={emailStatus} onValueChange={(v) => withReset(setEmailStatus)(v as LeadEmailStatus | "all")}>
              <SelectTrigger className="lg:w-44"><SelectValue placeholder="Any email" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any email</SelectItem>
                <SelectItem value="none">No email yet</SelectItem>
                <SelectItem value="captured">Email captured</SelectItem>
                <SelectItem value="sent">Email sent</SelectItem>
                <SelectItem value="failed">Email failed</SelectItem>
                <SelectItem value="replied">Replied</SelectItem>
              </SelectContent>
            </Select>
            <Select value={meetingStatus} onValueChange={(v) => withReset(setMeetingStatus)(v as LeadMeetingStatus | "all")}>
              <SelectTrigger className="lg:w-44"><SelectValue placeholder="Any meeting" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any meeting</SelectItem>
                <SelectItem value="none">No meeting</SelectItem>
                <SelectItem value="scheduled">Meeting scheduled</SelectItem>
                <SelectItem value="done">Meeting done</SelectItem>
                <SelectItem value="cancelled">Meeting cancelled</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {leads.isError ? (
        <ErrorBanner error={leads.error} onRetry={() => leads.refetch()} />
      ) : leads.isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No leads here yet"
          description="Leads appear automatically after campaign calls. You can also add one or import a CSV."
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <p className="text-sm font-semibold">{total} lead{total === 1 ? "" : "s"}</p>
            {total > PAGE && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
                <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>Prev</Button>
                <Button variant="outline" size="sm" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
              </div>
            )}
          </div>
          <CardContent className="overflow-x-auto p-0">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Lead</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last call</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Meeting</TableHead>
                  <TableHead>Owner</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((l) => (
                  <TableRow key={l.id}>
                    <TableCell className="min-w-48">
                      <Link to={`/leads/${l.id}`} className="block hover:underline">
                        <span className="font-medium">{l.name || "Unnamed"}</span>
                        {l.company && <span className="text-muted-foreground"> · {l.company}</span>}
                      </Link>
                      <span className="font-mono text-xs text-muted-foreground">{l.phone}</span>
                    </TableCell>
                    <TableCell>
                      <Select value={l.status} onValueChange={(v) => changeStatus(l.id, v as LeadStatus)}>
                        <SelectTrigger className="h-8 w-40 text-xs" aria-label={`Status of ${l.name || l.phone}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {LEAD_STATUSES.map((s) => <SelectItem key={s} value={s}>{titleCase(s)}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell className="min-w-56 max-w-sm">
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
                        <span className="flex items-center gap-1.5"><UserRound className="h-3.5 w-3.5" />{l.owner_name}</span>
                      ) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <AddLeadDialog open={addOpen} onOpenChange={setAddOpen} />
    </div>
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
