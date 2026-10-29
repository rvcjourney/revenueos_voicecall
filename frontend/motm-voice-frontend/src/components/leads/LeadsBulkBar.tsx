import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Download, Loader2, PhoneOutgoing, Tag, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ConfirmDialog } from "@/components/platform/ConfirmDialog";
import { leadsApi, apiErrorMessage } from "@/lib/api";
import { LEAD_STATUSES, type LeadBulkAction, type LeadFilters, type LeadsMeta } from "@/lib/types";
import { titleCase } from "@/lib/utils";

// Campaigns that can still take contacts (mirrors _CAN_ADD_TO in app/api/leads.py).
const OPEN_CAMPAIGN = new Set(["draft", "scheduled", "paused"]);

/** Shown above the table while rows are ticked: one action for all of them. */
export function LeadsBulkBar({
  ids, meta, filters, onDone,
}: { ids: string[]; meta: LeadsMeta | undefined; filters: LeadFilters; onDone: () => void }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [tag, setTag] = useState("");
  const [campaignOpen, setCampaignOpen] = useState(false);
  const [campaignId, setCampaignId] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const n = ids.length;

  async function run(action: LeadBulkAction, value?: string | null) {
    setBusy(true);
    try {
      const { data } = await leadsApi.bulk(ids, action, value);
      if (action === "add_to_campaign") {
        toast.success(`${data.added} added to “${data.campaign}”${data.skipped ? `, ${data.skipped} skipped (do-not-call or already in it)` : ""}`);
        setCampaignOpen(false);
      } else {
        toast.success(action === "delete" ? `${data.updated} deleted` : `${data.updated} lead${data.updated === 1 ? "" : "s"} updated`);
      }
      await qc.invalidateQueries({ queryKey: ["leads"] });
      onDone();
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't update the selected leads"));
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  }

  const campaigns = (meta?.campaigns ?? []).filter((c) => OPEN_CAMPAIGN.has(c.status));

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-primary/40 bg-primary/5 px-3 py-2" role="toolbar" aria-label="Bulk actions">
      <span className="mr-1 text-sm font-semibold">{n} selected</span>

      <Select value="" onValueChange={(v) => run("assign", v === "none" ? null : v)} disabled={busy}>
        <SelectTrigger className="h-8 w-36 text-xs"><SelectValue placeholder="Assign owner" /></SelectTrigger>
        <SelectContent>
          <SelectItem value="none">Unassigned</SelectItem>
          {meta?.members.map((m) => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}
        </SelectContent>
      </Select>
      <Select value="" onValueChange={(v) => run("status", v)} disabled={busy}>
        <SelectTrigger className="h-8 w-36 text-xs"><SelectValue placeholder="Change status" /></SelectTrigger>
        <SelectContent>{LEAD_STATUSES.map((s) => <SelectItem key={s} value={s}>{titleCase(s)}</SelectItem>)}</SelectContent>
      </Select>
      <Select value="" onValueChange={(v) => run("priority", v)} disabled={busy}>
        <SelectTrigger className="h-8 w-32 text-xs"><SelectValue placeholder="Priority" /></SelectTrigger>
        <SelectContent>
          <SelectItem value="hot">Hot</SelectItem>
          <SelectItem value="warm">Warm</SelectItem>
          <SelectItem value="cold">Cold</SelectItem>
        </SelectContent>
      </Select>
      <Input
        type="date" className="h-8 w-36 text-xs" aria-label="Set follow-up date" disabled={busy}
        onChange={(e) => e.target.value && run("follow_up", `${e.target.value}T10:00`)}
      />
      <form className="flex items-center gap-1" onSubmit={(e) => { e.preventDefault(); if (tag.trim()) run("tag", tag.trim()).then(() => setTag("")); }}>
        <Input className="h-8 w-28 text-xs" placeholder="Add tag" value={tag} onChange={(e) => setTag(e.target.value)} disabled={busy} />
        <Button type="submit" size="sm" variant="outline" className="h-8" disabled={busy || !tag.trim()} aria-label="Add tag"><Tag className="h-3.5 w-3.5" /></Button>
      </form>
      <Button size="sm" variant="outline" className="h-8" disabled={busy} onClick={() => setCampaignOpen(true)}>
        <PhoneOutgoing className="h-3.5 w-3.5" /> Call again
      </Button>
      <Button size="sm" variant="outline" className="h-8" disabled={busy}
        onClick={() => leadsApi.exportCsv(filters, ids).catch(() => toast.error("Export failed"))}>
        <Download className="h-3.5 w-3.5" /> Export
      </Button>
      <Button size="sm" variant="outline" className="h-8 text-destructive" disabled={busy} onClick={() => setConfirmDelete(true)}>
        <Trash2 className="h-3.5 w-3.5" /> Delete
      </Button>
      {busy && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
      <Button size="sm" variant="ghost" className="ml-auto h-8" onClick={onDone}><X className="h-3.5 w-3.5" /> Clear</Button>

      <Dialog open={campaignOpen} onOpenChange={setCampaignOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Call {n} lead{n === 1 ? "" : "s"} again</DialogTitle>
            <DialogDescription>
              They are added to a campaign that hasn't started (or is paused). Launch or resume it from Campaigns.
              Do-not-call leads and numbers already in that campaign are skipped.
            </DialogDescription>
          </DialogHeader>
          {campaigns.length === 0 ? (
            <p className="text-sm text-muted-foreground">No draft or paused campaign yet. Create one in Campaigns first.</p>
          ) : (
            <Select value={campaignId} onValueChange={setCampaignId}>
              <SelectTrigger><SelectValue placeholder="Pick a campaign" /></SelectTrigger>
              <SelectContent>
                {campaigns.map((c) => <SelectItem key={c.id} value={c.id}>{c.name} · {titleCase(c.status)}</SelectItem>)}
              </SelectContent>
            </Select>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setCampaignOpen(false)}>Cancel</Button>
            <Button variant="gradient" disabled={busy || !campaignId} onClick={() => run("add_to_campaign", campaignId)}>
              {busy && <Loader2 className="h-4 w-4 animate-spin" />} Add to campaign
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirmDelete} onOpenChange={setConfirmDelete} variant="destructive" loading={busy}
        title={`Delete ${n} lead${n === 1 ? "" : "s"}?`}
        description="They disappear from the list. If an agent calls the same number again, the lead comes back with its history."
        confirmLabel="Delete" onConfirm={() => run("delete")}
      />
    </div>
  );
}
