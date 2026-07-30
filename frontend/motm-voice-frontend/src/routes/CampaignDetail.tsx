import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft,
  Copy,
  Download,
  Loader2,
  Pause,
  Pencil,
  Phone,
  Play,
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
} from "@/lib/hooks";
import { campaignsApi } from "@/lib/api";
import { apiErrorMessage } from "@/lib/api";
import { callDurationSeconds, formatDate, formatDateTime, formatDuration } from "@/lib/utils";

export default function CampaignDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const campaign = useCampaign(id);
  const launch = useLaunchCampaign();
  const pause = usePauseCampaign();
  const duplicate = useDuplicateCampaign();
  const [editOpen, setEditOpen] = useState(false);

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

  async function handleDuplicate() {
    try {
      const res = await duplicate.mutateAsync(c.id);
      toast.success("Campaign duplicated");
      navigate(`/campaigns/${res.data.id}`);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't duplicate campaign"));
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
    } catch {
      toast.error("Export failed — is the backend reachable?");
    }
  }

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" asChild className="-ml-2">
        <Link to="/campaigns">
          <ArrowLeft className="h-4 w-4" /> Back to campaigns
        </Link>
      </Button>

      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <h1 className="font-heading text-2xl font-semibold sm:text-3xl">{c.name}</h1>
            <CampaignStatusBadge status={c.status} />
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
            <Pencil className="h-4 w-4" /> Edit
          </Button>
          <Button variant="outline" onClick={handleDuplicate} disabled={duplicate.isPending}>
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

      <Tabs defaultValue="overview">
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
          <ContactsTab campaignId={c.id} />
        </TabsContent>

        <TabsContent value="calls">
          <CallsTab campaignId={c.id} />
        </TabsContent>
      </Tabs>

      <EditCampaignDialog campaignId={c.id} initialNotes={c.notes ?? ""} open={editOpen} onOpenChange={setEditOpen} />
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

function ContactsTab({ campaignId }: { campaignId: string }) {
  const contacts = useCampaignContacts(campaignId, { limit: 100 });

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
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function CallsTab({ campaignId }: { campaignId: string }) {
  const calls = useCalls({ campaign_id: campaignId, limit: 100 });

  if (calls.isLoading) return <Skeleton className="h-64 w-full" />;
  if (calls.isError) return <ErrorBanner error={calls.error} onRetry={() => calls.refetch()} />;
  if (!calls.data || calls.data.length === 0) {
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
            {calls.data.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="font-mono text-xs">{row.phone_number}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{formatDateTime(row.started_at)}</TableCell>
                <TableCell>{formatDuration(callDurationSeconds(row))}</TableCell>
                <TableCell><CallOutcomeBadge outcome={row.outcome} /></TableCell>
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
