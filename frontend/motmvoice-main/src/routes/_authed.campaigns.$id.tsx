import { createFileRoute, Link, useParams, useNavigate } from "@tanstack/react-router";
import { CampaignBadge, OutcomeBadge } from "@/components/layout/StatusBadge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Pause, Play, ArrowLeft, Phone, Loader2, CheckCircle2, Heart, XCircle, Volume2, Download } from "lucide-react";
import { toast } from "sonner";
import { useCampaign, useCalls } from "@/lib/hooks";
import { campaignsApi, type CallOut } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";

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

  const { data: campaign, isLoading: campLoading } = useCampaign(id);
  const { data: callsData } = useCalls({ campaign_id: id, limit: 200 });

  const calls = callsData?.items ?? [];
  const interestedCalls = calls.filter((c) => c.outcome === "interested");
  const notInterestedCalls = calls.filter((c) =>
    ["not_interested", "do_not_call", "wrong_number"].includes(c.outcome)
  );

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

  if (campLoading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
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
          </div>
          {campaign.description && (
            <p className="text-sm text-muted-foreground mt-1">{campaign.description}</p>
          )}
        </div>
        <div className="flex gap-2">
          {campaign.status === "running" && (
            <Button variant="outline" size="sm" onClick={handlePause}>
              <Pause className="h-4 w-4" /> Pause
            </Button>
          )}
          {(campaign.status === "paused" || campaign.status === "draft") && (
            <Button size="sm" className="bg-gradient-primary text-white" onClick={handleLaunch}>
              <Play className="h-4 w-4" /> Launch
            </Button>
          )}
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-3 gap-3">
        <KPI icon={CheckCircle2} label="Calls Done" value={campaign.completed_calls} tone="text-primary" />
        <KPI icon={Heart} label="Interested" value={campaign.interested_count} tone="text-success" />
        <KPI icon={XCircle} label="Failed" value={campaign.failed_count} tone="text-destructive" />
      </div>

      {/* Progress bar */}
      <div className="rounded-xl bg-card border border-border p-5">
        <div className="flex items-center justify-between mb-2">
          <div className="font-semibold">Progress</div>
          <div className="font-mono text-sm">{pct}% — {campaign.completed_calls} / {campaign.total_contacts}</div>
        </div>
        <Progress value={pct} className="h-2.5" />
        <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground">
          <span>Window: {campaign.calling_window_start}–{campaign.calling_window_end} {campaign.timezone}</span>
          <span>Days: {campaign.calling_days.join(", ")}</span>
          <span>{campaign.calls_per_minute} call/min</span>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="calls">
        <TabsList className="bg-card border border-border">
          <TabsTrigger value="calls">Call History ({calls.length})</TabsTrigger>
          <TabsTrigger value="interested">
            <Heart className="h-3 w-3 mr-1 text-success" />
            Interested ({interestedCalls.length})
          </TabsTrigger>
          <TabsTrigger value="not_interested">
            <XCircle className="h-3 w-3 mr-1 text-destructive" />
            Not Interested ({notInterestedCalls.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="calls" className="mt-4">
          <CallTable calls={calls} emptyText="No calls made yet" />
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
          <CallTable calls={interestedCalls} emptyText="No interested leads yet" highlightPhone="text-success" />
        </TabsContent>

        <TabsContent value="not_interested" className="mt-4">
          <CallTable calls={notInterestedCalls} emptyText="No not-interested calls yet" highlightPhone="text-muted-foreground" />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function CallTable({
  calls,
  emptyText,
  highlightPhone = "",
}: {
  calls: CallOut[];
  emptyText: string;
  highlightPhone?: string;
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
              <th className="px-4 py-2 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {calls.map((c) => (
              <tr key={c.id} className="border-t border-border/60 hover:bg-surface-2/40 align-top">
                <td className={`px-4 py-3 font-mono text-xs ${highlightPhone}`}>{c.phone_number}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                  {c.started_at ? new Date(c.started_at).toLocaleString() : "—"}
                </td>
                <td className="px-4 py-3 font-mono text-xs whitespace-nowrap">{fmtDur(c.duration_seconds)}</td>
                <td className="px-4 py-3"><OutcomeBadge outcome={c.outcome} /></td>
                <td className="px-4 py-3">
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
                <td className="px-4 py-3 text-right">
                  <Link to="/calls/$id" params={{ id: c.id }}>
                    <Button variant="ghost" size="sm" className="h-7">
                      <Phone className="h-3 w-3" /> View
                    </Button>
                  </Link>
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
  return (
    <div className="rounded-xl bg-card border border-border p-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <div className="text-xs text-muted-foreground">{label}</div>
      </div>
      <div className={`text-2xl font-bold font-mono ${tone}`}>{value}</div>
    </div>
  );
}
