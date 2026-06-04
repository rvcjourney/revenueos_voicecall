import { createFileRoute, Link, useParams, useNavigate } from "@tanstack/react-router";
import { CampaignBadge, OutcomeBadge } from "@/components/layout/StatusBadge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Pause, Play, ArrowLeft, Phone, Loader2, CheckCircle2, Heart, XCircle, Volume2, Download, PhoneMissed, CalendarClock, Edit2, AlertTriangle, Copy, TrendingUp, FileText } from "lucide-react";
import { toast } from "sonner";
import { useCampaign, useCalls, useCall } from "@/lib/hooks";
import { campaignsApi, type CallOut, type CampaignOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useQueryClient } from "@tanstack/react-query";
import { useState, useEffect, useRef } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export const Route = createFileRoute("/_authed/campaigns/$id")({
  head: () => ({ meta: [{ title: "Campaign — MOTMVoice" }] }),
  component: CampaignDetail,
});

function fmtDur(s: number | null) {
  if (!s) return "—";
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}m ${String(r).padStart(2, "0")}s`;
}

function CampaignDetail() {
  const { id } = useParams({ from: "/_authed/campaigns/$id" });
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [showEdit, setShowEdit] = useState(false);
  const [selectedCallId, setSelectedCallId] = useState<string | null>(null);
  const [savingNotes, setSavingNotes] = useState(false);
  const [notes, setNotes] = useState<string | undefined>(undefined);
  const { isAdmin } = useAuth();

  const { data: campaign, isLoading: campLoading } = useCampaign(id);
  const { data: callsData } = useCalls({ campaign_id: id, limit: 200 });

  // Initialise notes from campaign once loaded
  if (campaign && notes === undefined) {
    setNotes(campaign.notes ?? "");
  }

  const calls = callsData?.items ?? [];
  const interestedCalls    = calls.filter((c) => c.outcome === "interested");
  const callbackCalls      = calls.filter((c) => c.outcome === "callback_requested");
  const notInterestedCalls = calls.filter((c) =>
    ["not_interested", "do_not_call", "wrong_number"].includes(c.outcome)
  );
  const noAnswerCalls = calls.filter((c) => c.outcome === "no_answer");

  async function handlePause() {
    try {
      await campaignsApi.pause(id);
      qc.invalidateQueries({ queryKey: ["campaigns", id] });
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      toast.success("Campaign paused");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to pause");
    }
  }

  async function handleLaunch() {
    try {
      await campaignsApi.launch(id);
      qc.invalidateQueries({ queryKey: ["campaigns", id] });
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      toast.success("Campaign launched");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to launch");
    }
  }

  async function handleDuplicate() {
    try {
      const { data: copy } = await campaignsApi.duplicate(id);
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      toast.success("Campaign duplicated — opening copy");
      navigate({ to: "/campaigns/$id", params: { id: copy.id } });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to duplicate");
    }
  }

  async function handleSaveNotes() {
    setSavingNotes(true);
    try {
      await campaignsApi.update(id, { notes: notes ?? "" });
      qc.invalidateQueries({ queryKey: ["campaigns", id] });
      toast.success("Notes saved");
    } catch {
      toast.error("Failed to save notes");
    } finally {
      setSavingNotes(false);
    }
  }

  if (campLoading) {
    return (
      <div className="space-y-6 max-w-[1600px]">
        <div className="h-8 w-64 rounded-lg bg-surface-2 animate-pulse" />
        <div className="grid grid-cols-3 gap-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-xl bg-card border border-border p-4 h-24 animate-pulse" style={{ animationDelay: `${i * 80}ms` }} />
          ))}
        </div>
        <div className="rounded-xl bg-card border border-border h-36 animate-pulse" />
        <div className="rounded-xl bg-card border border-border h-48 animate-pulse" style={{ animationDelay: "160ms" }} />
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="text-center py-20">
        <p className="text-muted-foreground">Campaign not found.</p>
        <Button variant="outline" className="mt-4" onClick={() => navigate({ to: "/campaigns" })}>
          Back to Campaigns
        </Button>
      </div>
    );
  }

  const pct = campaign.total_contacts > 0
    ? Math.round((campaign.completed_calls / campaign.total_contacts) * 100)
    : 0;

  // Funnel percentages
  const answeredCalls = interestedCalls.length + callbackCalls.length + notInterestedCalls.length;

  return (
    <div className="space-y-6 max-w-[1600px]">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <Link to="/campaigns" className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1 mb-2">
            <ArrowLeft className="h-3 w-3" /> Campaigns
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{campaign.name}</h1>
            <CampaignBadge status={campaign.status} />
            {campaign.status === "running" && (
              <span className="inline-flex items-center gap-1.5 text-[11px] text-success font-semibold">
                <span className="h-2 w-2 rounded-full bg-success animate-pulse" />
                Live
              </span>
            )}
          </div>
          {campaign.description && (
            <p className="text-sm text-muted-foreground mt-1">{campaign.description}</p>
          )}
        </div>
        <div className="flex gap-2 flex-wrap">
          {!isAdmin && campaign.status === "running" && (
            <>
              <Button variant="outline" size="sm" onClick={handlePause}>
                <Pause className="h-4 w-4" /> Pause
              </Button>
              <Button
                size="sm"
                className="bg-gradient-primary text-white"
                title="Re-dispatch the campaign dispatcher (use if calls have stopped)"
                onClick={handleLaunch}
              >
                <Play className="h-4 w-4" /> Restart
              </Button>
            </>
          )}
          {!isAdmin && campaign.status !== "completed" && (
            <Button
              variant="outline"
              size="sm"
              disabled={campaign.status === "running"}
              title={campaign.status === "running" ? "Pause the campaign before editing" : "Edit campaign settings"}
              onClick={() => setShowEdit(true)}
            >
              <Edit2 className="h-4 w-4" />
              {campaign.status === "running" ? "Pause to Edit" : "Edit"}
            </Button>
          )}
          {!isAdmin && (campaign.status === "paused" || campaign.status === "draft") && (
            <Button size="sm" className="bg-gradient-primary text-white" onClick={handleLaunch}>
              <Play className="h-4 w-4" /> Launch
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={handleDuplicate}>
            <Copy className="h-4 w-4" /> Duplicate
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              campaignsApi.exportAllResults(
                id,
                `${campaign.name.replace(/\s+/g, "_")}_full_results.csv`
              ).catch(() => toast.error("Export failed"))
            }
          >
            <Download className="h-4 w-4" /> Download CSV
          </Button>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-3 gap-3">
        <KPI icon={CheckCircle2} label="Calls Done" value={campaign.completed_calls} tone="text-primary" />
        <KPI icon={Heart} label="Interested" value={campaign.interested_count} tone="text-success" />
        <KPI icon={XCircle} label="Failed / DNC" value={campaign.failed_count} tone="text-destructive" />
      </div>

      {/* Progress + Funnel row */}
      <div className="grid lg:grid-cols-5 gap-4">
        {/* Progress */}
        <div className="lg:col-span-3 rounded-xl bg-card border border-border p-5">
          <div className="flex items-center justify-between mb-2">
            <div className="font-semibold">Progress</div>
            <div className="font-mono text-sm">{pct}% — {campaign.completed_calls} / {campaign.total_contacts}</div>
          </div>
          <Progress value={pct} className="h-2.5" />
          <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground flex-wrap">
            <span>Window: {campaign.calling_window_start}–{campaign.calling_window_end} {campaign.timezone}</span>
            <span>Days: {campaign.calling_days.join(", ")}</span>
            <span>{campaign.calls_per_minute} call/min</span>
            {campaign.created_by_name && (
              <span className="ml-auto font-medium text-foreground/70">
                Launched by: {campaign.created_by_name}
              </span>
            )}
            {campaign.started_at && (
              <span>Started: {new Date(campaign.started_at).toLocaleString()}</span>
            )}
            {campaign.completed_at && (
              <span>Completed: {new Date(campaign.completed_at).toLocaleString()}</span>
            )}
            {campaign.start_time && campaign.status === "scheduled" && (
              <span className="text-amber-400 font-medium">
                Scheduled: {new Date(campaign.start_time).toLocaleString()}
              </span>
            )}
          </div>
        </div>

        {/* Conversion funnel */}
        <div className="lg:col-span-2 rounded-xl bg-card border border-border p-5">
          <div className="font-semibold mb-4 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
            Conversion Funnel
          </div>
          <div className="space-y-3">
            <FunnelBar label="Total Contacts" value={campaign.total_contacts} max={campaign.total_contacts} color="bg-primary/40" />
            <FunnelBar label="Calls Made" value={campaign.completed_calls} max={campaign.total_contacts} color="bg-primary/70" />
            <FunnelBar label="Answered" value={answeredCalls} max={campaign.total_contacts} color="bg-amber-500/70" />
            <FunnelBar label="Interested" value={campaign.interested_count} max={campaign.total_contacts} color="bg-success/80" />
          </div>
        </div>
      </div>

      {/* Notes */}
      <div className="rounded-xl bg-card border border-border p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="font-semibold flex items-center gap-2">
            <FileText className="h-4 w-4 text-muted-foreground" />
            Campaign Notes
          </div>
          <Button size="sm" variant="outline" onClick={handleSaveNotes} disabled={savingNotes}>
            {savingNotes ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save"}
          </Button>
        </div>
        <Textarea
          placeholder="Add internal notes about this campaign — script feedback, follow-up tasks, observations…"
          rows={3}
          value={notes ?? ""}
          onChange={(e) => setNotes(e.target.value)}
          className="resize-none text-sm"
        />
      </div>

      {/* Tabs */}
      <Tabs defaultValue="calls">
        <TabsList className="bg-card border border-border">
          <TabsTrigger value="calls">Call History ({calls.length})</TabsTrigger>
          <TabsTrigger value="interested">
            <Heart className="h-3 w-3 mr-1 text-success" />
            Interested ({interestedCalls.length})
          </TabsTrigger>
          <TabsTrigger value="callback">
            <CalendarClock className="h-3 w-3 mr-1 text-amber-400" />
            Callback ({callbackCalls.length})
          </TabsTrigger>
          <TabsTrigger value="not_interested">
            <XCircle className="h-3 w-3 mr-1 text-destructive" />
            Not Interested ({notInterestedCalls.length})
          </TabsTrigger>
          <TabsTrigger value="no_answer">
            <PhoneMissed className="h-3 w-3 mr-1 text-muted-foreground" />
            No Answer ({noAnswerCalls.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="calls" className="mt-4">
          <CallTable calls={calls} emptyText="No calls made yet" onSelect={setSelectedCallId} />
        </TabsContent>

        <TabsContent value="interested" className="mt-4">
          {interestedCalls.length > 0 && (
            <div className="flex justify-end mb-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  campaignsApi.exportInterestedLeads(
                    id,
                    `${campaign.name.replace(/\s+/g, "_")}_interested_leads.csv`
                  ).catch(() => toast.error("Export failed"))
                }
              >
                <Download className="h-4 w-4 mr-1" /> Download CSV
              </Button>
            </div>
          )}
          <CallTable calls={interestedCalls} emptyText="No interested leads yet" highlightPhone="text-success" onSelect={setSelectedCallId} />
        </TabsContent>

        <TabsContent value="callback" className="mt-4">
          {callbackCalls.length > 0 && (
            <div className="flex justify-end mb-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  campaignsApi.exportCallbackLeads(
                    id,
                    `${campaign.name.replace(/\s+/g, "_")}_callback_leads.csv`
                  ).catch(() => toast.error("Export failed"))
                }
              >
                <Download className="h-4 w-4 mr-1" /> Download CSV
              </Button>
            </div>
          )}
          <CallTable calls={callbackCalls} emptyText="No callback requests yet" highlightPhone="text-amber-400" onSelect={setSelectedCallId} />
        </TabsContent>

        <TabsContent value="not_interested" className="mt-4">
          <CallTable calls={notInterestedCalls} emptyText="No not-interested calls yet" highlightPhone="text-muted-foreground" onSelect={setSelectedCallId} />
        </TabsContent>

        <TabsContent value="no_answer" className="mt-4">
          {noAnswerCalls.length > 0 && (
            <div className="flex justify-end mb-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  campaignsApi.exportNoAnswerCalls(
                    id,
                    `${campaign.name.replace(/\s+/g, "_")}_no_answer.csv`
                  ).catch(() => toast.error("Export failed"))
                }
              >
                <Download className="h-4 w-4 mr-1" /> Download CSV
              </Button>
            </div>
          )}
          <CallTable calls={noAnswerCalls} emptyText="No unanswered calls yet" highlightPhone="text-muted-foreground" onSelect={setSelectedCallId} />
        </TabsContent>
      </Tabs>

      {/* Edit Campaign Dialog */}
      {showEdit && campaign && (
        <EditCampaignDialog
          campaign={campaign}
          onClose={() => setShowEdit(false)}
          onSaved={() => {
            setShowEdit(false);
            qc.invalidateQueries({ queryKey: ["campaigns", id] });
            toast.success("Campaign updated");
          }}
        />
      )}

      {/* Call Detail Drawer */}
      <Sheet open={!!selectedCallId} onOpenChange={(o) => !o && setSelectedCallId(null)}>
        <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Call Detail</SheetTitle>
          </SheetHeader>
          {selectedCallId && <CallDetailPanel callId={selectedCallId} />}
        </SheetContent>
      </Sheet>
    </div>
  );
}

// ── Funnel Bar ────────────────────────────────────────────────────────────────

function FunnelBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono font-semibold">{value.toLocaleString()} <span className="text-muted-foreground font-normal">({pct}%)</span></span>
      </div>
      <div className="h-2 rounded-full bg-surface-2 overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// ── Call Detail Panel (inside Sheet) ─────────────────────────────────────────

function CallDetailPanel({ callId }: { callId: string }) {
  const { data: call, isLoading } = useCall(callId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!call) return <p className="text-muted-foreground text-sm mt-4">Call not found.</p>;

  const sentimentColor = call.sentiment === "positive" ? "text-success" : call.sentiment === "negative" ? "text-destructive" : "text-muted-foreground";

  return (
    <div className="space-y-5 mt-4">
      {/* Meta */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-xs text-muted-foreground">Phone</div>
          <div className="font-mono font-medium">{call.phone_number}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Outcome</div>
          <OutcomeBadge outcome={call.outcome} />
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Duration</div>
          <div className="font-mono">
            {call.duration_seconds ? `${Math.floor(call.duration_seconds / 60)}m ${call.duration_seconds % 60}s` : "—"}
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Sentiment</div>
          <div className={`font-semibold capitalize ${sentimentColor}`}>{call.sentiment ?? "—"}</div>
        </div>
        <div className="col-span-2">
          <div className="text-xs text-muted-foreground">Started</div>
          <div>{call.started_at ? new Date(call.started_at).toLocaleString() : "—"}</div>
        </div>
      </div>

      {/* Recording */}
      {call.recording_url && (
        <div>
          <div className="text-xs text-muted-foreground mb-1">Recording</div>
          <audio controls src={call.recording_url} className="w-full rounded-lg" />
        </div>
      )}

      {/* Summary */}
      {call.summary && (
        <div>
          <div className="text-xs text-muted-foreground mb-1">Summary</div>
          <div className="text-sm rounded-lg bg-surface-2 p-3 leading-relaxed">{call.summary}</div>
        </div>
      )}

      {/* Transcript */}
      {call.transcript_segments && call.transcript_segments.length > 0 && (
        <div>
          <div className="text-xs text-muted-foreground mb-2">Transcript</div>
          <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
            {call.transcript_segments.map((seg, i) => (
              <div key={i} className={`text-sm flex gap-2 ${seg.speaker === "agent" ? "flex-row" : "flex-row-reverse"}`}>
                <div className={`text-[10px] font-bold uppercase mt-0.5 shrink-0 w-10 text-center ${seg.speaker === "agent" ? "text-primary" : "text-amber-400"}`}>
                  {seg.speaker === "agent" ? "AI" : "User"}
                </div>
                <div className={`rounded-lg px-3 py-1.5 max-w-[85%] ${seg.speaker === "agent" ? "bg-primary/10 text-foreground" : "bg-surface-2 text-foreground"}`}>
                  {seg.text}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Extracted data */}
      {call.extracted_data && Object.keys(call.extracted_data).length > 0 && (
        <div>
          <div className="text-xs text-muted-foreground mb-1">Extracted Data</div>
          <div className="rounded-lg bg-surface-2 p-3 text-xs font-mono space-y-1">
            {Object.entries(call.extracted_data).map(([k, v]) => (
              <div key={k}><span className="text-primary">{k}:</span> {String(v)}</div>
            ))}
          </div>
        </div>
      )}

      <Link to="/calls/$id" params={{ id: callId }}>
        <Button variant="outline" size="sm" className="w-full">
          <Phone className="h-3 w-3" /> Open Full Call Page
        </Button>
      </Link>
    </div>
  );
}

// ── Edit Campaign Dialog ──────────────────────────────────────────────────────

const DAY_OPTS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"] as const;
const DAY_CODE: Record<string, string> = {
  Mon:"mon", Tue:"tue", Wed:"wed", Thu:"thu", Fri:"fri", Sat:"sat", Sun:"sun",
};

function EditCampaignDialog({
  campaign,
  onClose,
  onSaved,
}: {
  campaign: CampaignOut;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName]         = useState(campaign.name);
  const [desc, setDesc]         = useState(campaign.description ?? "");
  const [start, setStart]       = useState(campaign.calling_window_start.slice(0,5));
  const [end, setEnd]           = useState(campaign.calling_window_end.slice(0,5));
  const [tz, setTz]             = useState(campaign.timezone);
  const [cpm, setCpm]           = useState(String(campaign.calls_per_minute));
  const [retries, setRetries]   = useState(String(campaign.max_retries));
  const [days, setDays]         = useState<Record<string,boolean>>(
    Object.fromEntries(DAY_OPTS.map(d => [d, campaign.calling_days.includes(DAY_CODE[d])]))
  );
  const [saving, setSaving]     = useState(false);

  const canEdit = campaign.status === "paused" || campaign.status === "draft" || campaign.status === "scheduled";

  async function handleSave() {
    if (!canEdit) return;
    if (!name.trim()) { toast.error("Campaign name is required"); return; }
    const selectedDays = DAY_OPTS.filter(d => days[d]).map(d => DAY_CODE[d]);
    if (!selectedDays.length) { toast.error("Select at least one calling day"); return; }

    setSaving(true);
    try {
      await campaignsApi.update(campaign.id, {
        name:                 name.trim(),
        description:          desc || undefined,
        calling_window_start: start + ":00",
        calling_window_end:   end   + ":00",
        calling_days:         selectedDays,
        timezone:             tz,
        calls_per_minute:     parseInt(cpm) || 1,
        max_retries:          parseInt(retries) || 1,
      });
      onSaved();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Edit2 className="h-4 w-4" /> Edit Campaign
          </DialogTitle>
        </DialogHeader>

        {!canEdit && (
          <div className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/8 px-4 py-3 text-sm text-amber-300">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>Pause the campaign before making changes. Running campaigns cannot be edited.</span>
          </div>
        )}

        <div className="space-y-4 py-1">
          <div className="space-y-1.5">
            <Label>Campaign Name</Label>
            <Input value={name} onChange={e => setName(e.target.value)} disabled={!canEdit} />
          </div>
          <div className="space-y-1.5">
            <Label>Description <span className="text-muted-foreground text-xs">(optional)</span></Label>
            <Input value={desc} onChange={e => setDesc(e.target.value)} disabled={!canEdit} placeholder="e.g. Q3 outbound drive" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Start Time</Label>
              <Input type="time" value={start} onChange={e => setStart(e.target.value)} disabled={!canEdit} />
            </div>
            <div className="space-y-1.5">
              <Label>End Time</Label>
              <Input type="time" value={end} onChange={e => setEnd(e.target.value)} disabled={!canEdit} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Timezone</Label>
            <Select value={tz} onValueChange={setTz} disabled={!canEdit}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {["Asia/Kolkata","Asia/Dubai","Asia/Singapore","Asia/Tokyo",
                  "Europe/London","America/New_York","America/Los_Angeles","UTC"].map(t => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Calling Days</Label>
            <div className="flex flex-wrap gap-2">
              {DAY_OPTS.map(d => (
                <button
                  key={d}
                  type="button"
                  disabled={!canEdit}
                  onClick={() => setDays(prev => ({ ...prev, [d]: !prev[d] }))}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
                    days[d]
                      ? "bg-primary/20 border-primary/60 text-primary"
                      : "border-border text-muted-foreground hover:border-primary/40"
                  } disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Calls / Minute</Label>
              <Select value={cpm} onValueChange={setCpm} disabled={!canEdit}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["1","2","3","5","10"].map(v => (
                    <SelectItem key={v} value={v}>{v}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Max Retries</Label>
              <Select value={retries} onValueChange={setRetries} disabled={!canEdit}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["0","1","2","3"].map(v => (
                    <SelectItem key={v} value={v}>{v}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            className="bg-gradient-primary text-white"
            onClick={handleSave}
            disabled={!canEdit || saving}
          >
            {saving ? <><Loader2 className="h-4 w-4 animate-spin" /> Saving…</> : "Save Changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const OUTCOME_STRIPE: Record<string, string> = {
  interested:         "oklch(0.70 0.16 160)",
  callback_requested: "oklch(0.75 0.16 75)",
  not_interested:     "oklch(0.60 0.18 25)",
  do_not_call:        "oklch(0.60 0.18 25)",
  wrong_number:       "oklch(0.60 0.18 25)",
  failed:             "oklch(0.60 0.18 25)",
  no_answer:          "oklch(0.42 0.01 270)",
  voicemail:          "oklch(0.42 0.01 270)",
};

function CallTable({
  calls,
  emptyText,
  highlightPhone = "",
  onSelect,
}: {
  calls: CallOut[];
  emptyText: string;
  highlightPhone?: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="rounded-xl bg-card border border-border overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground bg-surface-2/40">
              <th className="px-4 py-2 font-medium">Phone</th>
              <th className="px-4 py-2 font-medium">Started</th>
              <th className="px-4 py-2 font-medium">Duration</th>
              <th className="px-4 py-2 font-medium">Outcome</th>
              <th className="px-4 py-2 font-medium">Recording</th>
              <th className="px-4 py-2 font-medium">Summary</th>
              <th className="px-4 py-2 font-medium text-right">Detail</th>
            </tr>
          </thead>
          <tbody>
            {calls.map((c) => (
              <tr
                key={c.id}
                className="border-t border-border/60 hover:bg-surface-2/40 align-top cursor-pointer"
                onClick={() => onSelect(c.id)}
              >
                <td
                  className={`px-4 py-3 font-mono text-xs ${highlightPhone}`}
                  style={{ borderLeft: `3px solid ${OUTCOME_STRIPE[c.outcome] ?? "transparent"}` }}
                >
                  {c.phone_number}
                </td>
                <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                  {c.started_at ? new Date(c.started_at).toLocaleString() : "—"}
                </td>
                <td className="px-4 py-3 font-mono text-xs whitespace-nowrap">{fmtDur(c.duration_seconds)}</td>
                <td className="px-4 py-3"><OutcomeBadge outcome={c.outcome} /></td>
                <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                  {c.recording_url ? (
                    <a
                      href={c.recording_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                    >
                      <Volume2 className="h-3 w-3" /> Play
                    </a>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-muted-foreground max-w-sm">
                  {c.summary ? (
                    <span title={c.summary} className="line-clamp-2">{c.summary}</span>
                  ) : (
                    <span className="italic">Pending…</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                  <Button variant="ghost" size="sm" className="h-7" onClick={() => onSelect(c.id)}>
                    <Phone className="h-3 w-3" /> View
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {calls.length === 0 && (
        <div className="p-12 text-center text-muted-foreground text-sm">{emptyText}</div>
      )}
    </div>
  );
}

function KPI({ icon: Icon, label, value, tone = "" }: { icon: any; label: string; value: number; tone?: string }) {
  const [display, setDisplay] = useState(value);
  const [flash, setFlash]     = useState(false);
  const rafRef  = useRef(0);
  const prevRef = useRef({ value, display: value });

  useEffect(() => {
    if (value === prevRef.current.value) return;
    const startVal = prevRef.current.display;
    prevRef.current.value = value;
    setFlash(true);
    const startTime = performance.now();
    cancelAnimationFrame(rafRef.current);
    function tick(now: number) {
      const p = Math.min((now - startTime) / 600, 1);
      const e = 1 - Math.pow(1 - p, 3);
      const n = Math.round(startVal + (value - startVal) * e);
      prevRef.current.display = n;
      setDisplay(n);
      if (p < 1) rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    const t = setTimeout(() => setFlash(false), 1500);
    return () => { cancelAnimationFrame(rafRef.current); clearTimeout(t); };
  }, [value]);

  return (
    <div className={`rounded-xl border p-4 transition-all duration-500 ${flash ? "border-primary/50 bg-primary/[0.03]" : "bg-card border-border"}`}>
      <div className="flex items-center gap-2 mb-2">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <div className="text-xs text-muted-foreground">{label}</div>
      </div>
      <div className={`text-2xl font-bold font-mono ${tone}`}>{display}</div>
    </div>
  );
}
