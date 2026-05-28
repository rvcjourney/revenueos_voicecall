import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { OutcomeBadge } from "@/components/layout/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Search, Phone, Loader2 } from "lucide-react";
import { useCalls, useCampaigns } from "@/lib/hooks";

export const Route = createFileRoute("/_authed/calls/")({
  head: () => ({ meta: [{ title: "Call History — MOTMVoice" }] }),
  component: CallHistory,
});

function fmtDur(s: number | null) {
  if (!s) return "—";
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}m ${String(r).padStart(2, "0")}s`;
}

function CallHistory() {
  const [campaignF, setCampaignF] = useState("all");
  const [outcomeF, setOutcomeF] = useState("all");
  const [q, setQ] = useState("");

  const { data: callsData, isLoading } = useCalls({
    campaign_id: campaignF !== "all" ? campaignF : undefined,
    outcome: outcomeF !== "all" ? outcomeF : undefined,
    limit: 200,
  });
  const { data: campaignsData } = useCampaigns();

  const campaigns = campaignsData?.items ?? [];
  const campaignMap = Object.fromEntries(campaigns.map((c) => [c.id, c.name]));

  const calls = (callsData?.items ?? []).filter(
    (c) => q === "" || c.phone_number.includes(q)
  );

  return (
    <div className="space-y-6 max-w-[1700px]">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Call History</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {callsData?.total ?? 0} total calls
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Select value={campaignF} onValueChange={setCampaignF}>
          <SelectTrigger className="w-56">
            <SelectValue placeholder="All campaigns" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Campaigns</SelectItem>
            {campaigns.map((c) => (
              <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={outcomeF} onValueChange={setOutcomeF}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="All outcomes" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Outcomes</SelectItem>
            {["interested", "callback_requested", "not_interested", "no_answer", "failed", "do_not_call", "wrong_number", "voicemail"].map((o) => (
              <SelectItem key={o} value={o}>{o.replace(/_/g, " ")}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by phone…"
            className="pl-9"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>

      <div className="rounded-xl bg-card border border-border overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground bg-surface-2/60 sticky top-0">
                  <th className="px-4 py-3 font-medium">Phone</th>
                  <th className="px-4 py-3 font-medium">Campaign</th>
                  <th className="px-4 py-3 font-medium">Started</th>
                  <th className="px-4 py-3 font-medium">Duration</th>
                  <th className="px-4 py-3 font-medium">Outcome</th>
                  <th className="px-4 py-3 font-medium text-right">Cost (₹)</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((c) => (
                  <tr key={c.id} className="border-t border-border/60 hover:bg-surface-2/40">
                    <td className="px-4 py-3 font-mono text-xs">{c.phone_number}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">
                      {c.campaign_id ? (campaignMap[c.campaign_id] ?? "—") : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                      {c.started_at ? new Date(c.started_at).toLocaleString() : "—"}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{fmtDur(c.duration_seconds)}</td>
                    <td className="px-4 py-3"><OutcomeBadge outcome={c.outcome} /></td>
                    <td className="px-4 py-3 text-right font-mono text-xs">
                      {c.cost_inr != null ? c.cost_inr.toFixed(2) : "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link to="/calls/$id" params={{ id: c.id }}>
                        <Button size="sm" variant="ghost" className="h-7">
                          <Phone className="h-3 w-3" /> View
                        </Button>
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {calls.length === 0 && (
              <div className="p-12 text-center text-muted-foreground text-sm">
                No calls found
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
