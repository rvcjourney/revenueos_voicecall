import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { CampaignBadge } from "@/components/layout/StatusBadge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Search, Calendar, Users, CheckCircle2, Heart, MoreVertical, Pause, Play, Loader2 } from "lucide-react";
import { useCampaigns } from "@/lib/hooks";
import { campaignsApi } from "@/lib/api";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";

export const Route = createFileRoute("/_authed/campaigns/")({
  head: () => ({ meta: [{ title: "Campaigns — MOTMVoice" }] }),
  component: CampaignsList,
});

const FILTER_TABS = [
  { v: "all", l: "All" },
  { v: "running", l: "Active" },
  { v: "paused", l: "Paused" },
  { v: "completed", l: "Completed" },
  { v: "draft", l: "Draft" },
];

function CampaignsList() {
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const qc = useQueryClient();

  const { data, isLoading } = useCampaigns(filter === "all" ? undefined : filter);
  const campaigns = (data?.items ?? []).filter((c) =>
    c.name.toLowerCase().includes(q.toLowerCase())
  );

  async function handlePause(id: string) {
    try {
      await campaignsApi.pause(id);
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      toast.success("Campaign paused");
    } catch {
      toast.error("Failed to pause campaign");
    }
  }

  async function handleLaunch(id: string) {
    try {
      await campaignsApi.launch(id);
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      toast.success("Campaign launched");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to launch campaign");
    }
  }

  return (
    <div className="space-y-6 max-w-[1600px]">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Campaigns</h1>
          <p className="text-sm text-muted-foreground mt-1">Manage your AI calling campaigns</p>
        </div>
        <Link to="/campaigns/new">
          <Button className="bg-gradient-primary text-white shadow-glow">
            <Plus className="h-4 w-4" /> Create New Campaign
          </Button>
        </Link>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 p-1 rounded-lg bg-surface-2 border border-border">
          {FILTER_TABS.map((f) => (
            <button
              key={f.v}
              onClick={() => setFilter(f.v)}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                filter === f.v ? "bg-primary/15 text-foreground" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {f.l}
            </button>
          ))}
        </div>
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search campaigns…" className="pl-9" />
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : campaigns.length === 0 ? (
        <div className="text-center py-20 rounded-xl bg-card border border-border">
          <div className="text-4xl mb-4">📋</div>
          <h3 className="font-semibold text-lg">No campaigns yet</h3>
          <p className="text-sm text-muted-foreground mt-1 mb-6">Create your first AI calling campaign to get started</p>
          <Link to="/campaigns/new">
            <Button className="bg-gradient-primary text-white shadow-glow">
              <Plus className="h-4 w-4" /> Create Campaign
            </Button>
          </Link>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
          {campaigns.map((c) => {
            const pct = c.total_contacts > 0 ? Math.round((c.completed_calls / c.total_contacts) * 100) : 0;
            return (
              <div key={c.id} className="rounded-xl bg-card border border-border p-5 hover:border-primary/40 transition-colors group">
                <div className="flex items-start justify-between mb-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <CampaignBadge status={c.status} />
                    </div>
                    <Link
                      to="/campaigns/$id"
                      params={{ id: c.id }}
                      className="font-semibold hover:text-primary block truncate"
                    >
                      {c.name}
                    </Link>
                    {c.description && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{c.description}</p>
                    )}
                  </div>
                  <button className="text-muted-foreground hover:text-foreground">
                    <MoreVertical className="h-4 w-4" />
                  </button>
                </div>

                <div className="grid grid-cols-4 gap-2 my-4 text-center">
                  <Stat icon={Users} v={c.total_contacts} l="Total" />
                  <Stat icon={CheckCircle2} v={c.completed_calls} l="Done" />
                  <Stat icon={Heart} v={c.interested_count} l="Hot" hot />
                  <Stat v={`${pct}%`} l="Progress" />
                </div>

                <Progress value={pct} className="h-1.5" />
                <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
                  <span className="font-mono">{pct}%</span>
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    {new Date(c.created_at).toLocaleDateString()}
                  </span>
                </div>

                <div className="mt-4 flex gap-2">
                  <Link to="/campaigns/$id" params={{ id: c.id }} className="flex-1">
                    <Button variant="outline" size="sm" className="w-full">View Details</Button>
                  </Link>
                  {c.status === "running" ? (
                    <Button variant="ghost" size="sm" onClick={() => handlePause(c.id)}>
                      <Pause className="h-3.5 w-3.5" />
                    </Button>
                  ) : c.status === "paused" || c.status === "draft" ? (
                    <Button variant="ghost" size="sm" onClick={() => handleLaunch(c.id)}>
                      <Play className="h-3.5 w-3.5" />
                    </Button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Stat({ icon: Icon, v, l, hot }: { icon?: any; v: any; l: string; hot?: boolean }) {
  return (
    <div className="rounded-md bg-surface-2/60 py-2">
      <div className={`text-sm font-mono font-semibold ${hot ? "text-success" : ""}`}>{v}</div>
      <div className="text-[10px] text-muted-foreground uppercase tracking-wider mt-0.5">{l}</div>
    </div>
  );
}
