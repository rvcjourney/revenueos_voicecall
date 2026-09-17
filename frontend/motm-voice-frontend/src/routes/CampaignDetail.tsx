import { useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft,
  Copy,
  Sparkles,
  Download,
  Loader2,
  Pause,
  Phone,
  Play,
  StickyNote,
  Users,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { CallOutcomeBadge, CampaignStatusBadge, ContactStatusBadge } from "@/components/shared/StatusBadge";
import {
  useCampaign,
  useCampaignContacts,
  useCalls,
  useDuplicateCampaign,
  useLaunchCampaign,
  usePauseCampaign,
  useUpdateCampaign,
  useUploadContacts,
} from "@/lib/hooks";
import { campaignsApi, usageApi } from "@/lib/api";
import { apiErrorMessage } from "@/lib/api";
import { callDurationSeconds, cn, formatDate, formatDateTime, formatDuration } from "@/lib/utils";
import type { CampaignContact } from "@/lib/types";

export default function CampaignDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const campaign = useCampaign(id);
  const launch = useLaunchCampaign();
  const pause = usePauseCampaign();
  const [editOpen, setEditOpen] = useState(false);
  const [dupOpen, setDupOpen] = useState(false);

  if (campaign.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (campaign.isError || !campaign.data) {
    return <ErrorBanner error={campaign.error} onRetry={() => campaign.refetch()} />;
  }

  const c = campaign.data;
  const canLaunch = c.status === "draft" || c.status === "paused";
  const canPause = c.status === "running";
  const progressPct = c.total_contacts ? Math.round((c.completed_calls / c.total_contacts) * 100) : 0;

  async function handleLaunch() {
    if (c.total_contacts === 0) {
      toast.error("Upload contacts before launching this campaign.");
      return;
    }
    try {
      await launch.mutateAsync(c.id);
      toast.success("Campaign launched");
      // Give the dispatcher a moment to start dialing and hit the per-user
      // 1-call-at-a-time cap (if this user already has another call running)
      // before we check — an immediate check would always read 0.
      setTimeout(async () => {
        try {
          const { data } = await usageApi.concurrency();
          if (data.my_queued > 0) {
            toast.info(
              "You already have a call in progress — since you can only have 1 call active at a time, this campaign's calls will queue and dial automatically as your current one finishes."
            );
          }
        } catch {
          // best-effort UX hint only — never surface this check's own failure
        }
      }, 5000);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't launch campaign"));
    }
  }

  async function handlePause() {
    try {
      await pause.mutateAsync(c.id);
      toast.success("Campaign paused");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't pause campaign"));
    }
  }

  async function handleExport(kind: "interested" | "no_answer" | "callback_requested" | "all") {
    try {
      const filename = `${c.name.replace(/\s+/g, "-")}-${kind}.csv`;
      if (kind === "interested") await campaignsApi.exportInterested(c.id, filename);
      if (kind === "no_answer") await campaignsApi.exportNoAnswer(c.id, filename);
      if (kind === "callback_requested") await campaignsApi.exportCallbacks(c.id, filename);
      if (kind === "all") await campaignsApi.exportAll(c.id, filename);
      toast.success("Export downloaded");
    } catch (err) {
      // downloadBlob() uses fetch(), not axios, so apiErrorMessage() (which only
      // understands axios errors) won't parse this — its message is already the
      // real backend detail (see downloadBlob in lib/api.ts).
      toast.error(err instanceof Error ? err.message : "Export failed — is the backend reachable?");
    }
  }

  const activeTab = searchParams.get("tab") ?? "overview";
  function handleTabChange(tab: string) {
    // replace: true -- switching tabs shouldn't itself be a back-button stop,
    // it just keeps the URL (and so browser history) pointing at whichever
    // tab is currently open, so returning here later (e.g. from a call's
    // detail page) restores that tab instead of resetting to Overview.
    setSearchParams(tab === "overview" ? {} : { tab }, { replace: true });
  }

  // Campaigns list is the only place this page is ever linked from today, but
  // true back-navigation (matching the fix in CallDetail.tsx) is still more
  // correct than a hardcoded destination, and avoids piling up redundant
  // history entries. Same "no real history" fallback as CallDetail.
  function handleBack() {
    if (location.key !== "default") navigate(-1);
    else navigate(c.is_prime ? "/prime-calling" : "/campaigns");
  }

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" onClick={handleBack} className="-ml-2">
        <ArrowLeft className="h-4 w-4" /> Back to campaigns
      </Button>

      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <h1 className="font-heading text-2xl font-semibold sm:text-3xl">{c.name}</h1>
            <CampaignStatusBadge status={c.status} />
            {c.is_prime && (
              <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
                <Sparkles className="h-3 w-3" /> Prime
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            {c.description || "No description"} · Created by {c.created_by_name ?? "—"} on {formatDate(c.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canLaunch && (
            <Button variant="gradient" onClick={handleLaunch} disabled={launch.isPending}>
              {launch.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              Launch
            </Button>
          )}
          {canPause && (
            <Button variant="outline" onClick={handlePause} disabled={pause.isPending}>
              {pause.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Pause className="h-4 w-4" />}
              Pause
            </Button>
          )}
          <Button variant="outline" onClick={() => setEditOpen(true)}>
            <StickyNote className="h-4 w-4" /> Notes
          </Button>
          <Button variant="outline" onClick={() => setDupOpen(true)}>
            <Copy className="h-4 w-4" /> Duplicate
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline">
                <Download className="h-4 w-4" /> Export
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => handleExport("interested")}>Interested leads</DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleExport("callback_requested")}>Callback requests</DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleExport("no_answer")}>No-answer calls</DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleExport("all")}>All results</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={Users} label="Total Contacts" value={c.total_contacts} />
        <StatCard icon={Phone} label="Completed Calls" value={c.completed_calls} sub={`${progressPct}% done`} />
        <StatCard icon={Phone} label="Interested" value={c.interested_count} tone="success" />
        <StatCard icon={Phone} label="Failed" value={c.failed_count} tone={c.failed_count > 0 ? "destructive" : undefined} />
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="contacts">Contacts</TabsTrigger>
          <TabsTrigger value="calls">Calls</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <Card>
            <CardContent className="grid gap-6 pt-6 sm:grid-cols-2">
              <InfoRow label="Goal" value={c.goal.replace("_", " ")} />
              <InfoRow label="Calling window" value={`${c.calling_window_start} – ${c.calling_window_end} (${c.timezone})`} />
              <InfoRow label="Calling days" value={c.calling_days.map((d) => d.toUpperCase()).join(", ") || "—"} />
              <InfoRow label="Pace" value={`${c.calls_per_minute} calls/min · ${c.max_retries} retries`} />
              <InfoRow label="Started" value={formatDateTime(c.started_at)} />
              <InfoRow label="Completed" value={formatDateTime(c.completed_at)} />
              <div className="sm:col-span-2">
                <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Notes</p>
                <p className="text-sm text-foreground/90">{c.notes || "No notes yet."}</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="contacts">
          <ContactsTab campaignId={c.id} isPrime={c.is_prime} />
        </TabsContent>

        <TabsContent value="calls">
          <CallsTab campaignId={c.id} />
        </TabsContent>
      </Tabs>

      <EditCampaignDialog campaignId={c.id} initialNotes={c.notes ?? ""} open={editOpen} onOpenChange={setEditOpen} />
      <DuplicateCampaignDialog campaignId={c.id} campaignName={c.name} open={dupOpen} onOpenChange={setDupOpen} />
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  tone,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  sub?: string;
  tone?: "success" | "destructive";
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 pt-6">
        <span
          className={`flex h-10 w-10 items-center justify-center rounded-xl ${
            tone === "success" ? "bg-success/15 text-success" : tone === "destructive" ? "bg-destructive/15 text-destructive" : "bg-primary/15 text-primary"
          }`}
        >
          <Icon className="h-5 w-5" />
        </span>
        <div>
          <p className="font-heading text-2xl font-semibold">{value.toLocaleString()}</p>
          <p className="text-xs text-muted-foreground">{sub ?? label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-sm capitalize">{value}</p>
    </div>
  );
}

function ContactsTab({ campaignId, isPrime }: { campaignId: string; isPrime: boolean }) {
  const contacts = useCampaignContacts(campaignId, { limit: 100 });
  const [promptRow, setPromptRow] = useState<CampaignContact | null>(null);

  if (contacts.isLoading) return <Skeleton className="h-64 w-full" />;
  if (contacts.isError) return <ErrorBanner error={contacts.error} onRetry={() => contacts.refetch()} />;
  if (!contacts.data || contacts.data.items.length === 0) {
    return <EmptyState icon={Users} title="No contacts uploaded" description="Upload a CSV of contacts to this campaign to get started." />;
  }

  return (
    <Card>
      <CardContent className="pt-6">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Attempts</TableHead>
              <TableHead>Last attempted</TableHead>
              {isPrime && <TableHead>AI prompt</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {contacts.data.items.map((row) => (
              <TableRow key={row.id}>
                <TableCell>{row.name || "—"}</TableCell>
                <TableCell className="font-mono text-xs">{row.phone}</TableCell>
                <TableCell>{row.company || "—"}</TableCell>
                <TableCell><ContactStatusBadge status={row.status} /></TableCell>
                <TableCell>{row.attempt_count}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{formatDateTime(row.last_attempted_at)}</TableCell>
                {isPrime && (
                  <TableCell>
                    {row.generated_system_prompt || row.prompt_error ? (
                      <Button variant="ghost" size="sm" onClick={() => setPromptRow(row)}>
                        {row.generated_system_prompt ? "View" : <span className="text-warning">Fallback used</span>}
                      </Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">Written at call time</span>
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
      <Dialog open={!!promptRow} onOpenChange={(open) => !open && setPromptRow(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>AI prompt for {promptRow?.name}</DialogTitle>
          </DialogHeader>
          {promptRow?.prompt_error && !promptRow.generated_system_prompt && (
            <p className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs">
              The AI couldn't write a personalised prompt, so this call used the agent's normal prompt plus the
              contact's details. Reason: {promptRow.prompt_error}
            </p>
          )}
          {promptRow?.generated_welcome_message && (
            <div className="space-y-1.5">
              <Label>Welcome message</Label>
              <p className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm">
                {promptRow.generated_welcome_message}
              </p>
            </div>
          )}
          {promptRow?.generated_system_prompt && (
            <div className="space-y-1.5">
              <Label>Prompt</Label>
              <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-muted/40 p-3 font-sans text-xs leading-relaxed">
                {promptRow.generated_system_prompt}
              </pre>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function CallsTab({ campaignId }: { campaignId: string }) {
  const calls = useCalls({ campaign_id: campaignId, limit: 100 });

  if (calls.isLoading) return <Skeleton className="h-64 w-full" />;
  if (calls.isError) return <ErrorBanner error={calls.error} onRetry={() => calls.refetch()} />;
  const rows = calls.data?.items ?? [];
  if (rows.length === 0) {
    return <EmptyState icon={Phone} title="No calls yet" description="Calls will appear here once this campaign starts dialing." />;
  }

  return (
    <Card>
      <CardContent className="pt-6">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Phone</TableHead>
              <TableHead>Started</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Outcome</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="font-mono text-xs">{row.phone_number}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{formatDateTime(row.started_at)}</TableCell>
                <TableCell>{formatDuration(callDurationSeconds(row))}</TableCell>
                <TableCell><CallOutcomeBadge outcome={row.outcome} status={row.status} /></TableCell>
                <TableCell className="text-right">
                  <Button variant="ghost" size="sm" asChild>
                    <Link to={`/calls/${row.id}`}>View</Link>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function EditCampaignDialog({
  campaignId,
  initialNotes,
  open,
  onOpenChange,
}: {
  campaignId: string;
  initialNotes: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const [notes, setNotes] = useState(initialNotes);
  const updateCampaign = useUpdateCampaign();

  async function save() {
    try {
      await updateCampaign.mutateAsync({ id: campaignId, data: { notes } });
      toast.success("Campaign updated");
      onOpenChange(false);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't update campaign"));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit campaign notes</DialogTitle>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="notes">Notes</Label>
          <Textarea id="notes" rows={5} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="gradient" onClick={save} disabled={updateCampaign.isPending}>
            {updateCampaign.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Save changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DuplicateCampaignDialog({
  campaignId,
  campaignName,
  open,
  onOpenChange,
}: {
  campaignId: string;
  campaignName: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const [mode, setMode] = useState<"existing" | "new" | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const navigate = useNavigate();
  const duplicate = useDuplicateCampaign();
  const uploadContacts = useUploadContacts();
  const launchCampaign = useLaunchCampaign();
  const busy = duplicate.isPending || uploadContacts.isPending || launchCampaign.isPending;

  function reset() {
    setMode(null);
    setFile(null);
  }

  async function handleConfirm() {
    if (mode === "existing") {
      try {
        const res = await duplicate.mutateAsync({ id: campaignId, copyContacts: true });
        toast.success("Campaign duplicated");
        onOpenChange(false);
        reset();
        navigate(`/campaigns/${res.data.id}`);
      } catch (err) {
        toast.error(apiErrorMessage(err, "Couldn't duplicate campaign"));
      }
      return;
    }

    if (mode === "new") {
      if (!file) {
        toast.error("Choose a CSV or Excel file first");
        return;
      }
      // Three steps against a brand-new campaign: create it empty (copy_contacts=
      // false -- see the backend's own note on why skipping the copy matters
      // here, since uploads append rather than replace), upload the chosen file,
      // then launch. If a later step fails, the campaign from the earlier steps
      // still exists -- navigate to it either way so nothing is stranded off-screen,
      // just with a message pointing at what still needs finishing manually.
      let newId: string | null = null;
      try {
        const dup = await duplicate.mutateAsync({ id: campaignId, copyContacts: false });
        newId = dup.data.id;
        await uploadContacts.mutateAsync({ id: newId, file });
        await launchCampaign.mutateAsync(newId);
        toast.success("Campaign duplicated and launched with the new contact list");
        onOpenChange(false);
        reset();
        navigate(`/campaigns/${newId}`);
      } catch (err) {
        toast.error(
          apiErrorMessage(
            err,
            "Duplicate created, but uploading/launching with the new contacts didn't finish — pick up from the new campaign's page"
          )
        );
        if (newId) {
          onOpenChange(false);
          reset();
          navigate(`/campaigns/${newId}`);
        }
      }
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) reset();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Duplicate "{campaignName}"</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Should the new campaign keep this campaign's contacts, or start fresh with a new list?
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => setMode("existing")}
              className={cn(
                "rounded-lg border p-3 text-left text-sm transition-colors",
                mode === "existing" ? "border-primary bg-primary/5" : "border-border hover:bg-muted/30"
              )}
            >
              <p className="font-medium">Keep existing contacts</p>
              <p className="text-xs text-muted-foreground">Copies the same contact list into the new draft.</p>
            </button>
            <button
              type="button"
              onClick={() => setMode("new")}
              className={cn(
                "rounded-lg border p-3 text-left text-sm transition-colors",
                mode === "new" ? "border-primary bg-primary/5" : "border-border hover:bg-muted/30"
              )}
            >
              <p className="font-medium">Upload new contacts</p>
              <p className="text-xs text-muted-foreground">Starts empty — upload a CSV, then it launches automatically.</p>
            </button>
          </div>

          {mode === "new" && (
            <div className="space-y-1.5">
              <Label htmlFor="dup-file">Contact file</Label>
              <input
                id="dup-file"
                type="file"
                accept=".csv,.xlsx,.xls"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-secondary file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-secondary-foreground hover:file:bg-secondary/80"
              />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="gradient" onClick={handleConfirm} disabled={!mode || (mode === "new" && !file) || busy}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {mode === "new" ? "Duplicate & launch" : "Duplicate"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
