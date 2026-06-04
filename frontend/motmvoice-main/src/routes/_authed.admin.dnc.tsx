import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, useEffect, useCallback } from "react";
import { adminApi, type DncEntry } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { PhoneOff, Plus, Trash2, Search, Loader2, Shield } from "lucide-react";

export const Route = createFileRoute("/_authed/admin/dnc")({
  head: () => ({ meta: [{ title: "DNC List — MOTMVoice" }] }),
  component: DncPage,
});

function DncPage() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();

  const [entries, setEntries] = useState<DncEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [showAdd, setShowAdd] = useState(false);

  useEffect(() => {
    if (!isAdmin) navigate({ to: "/dashboard" });
  }, [isAdmin, navigate]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await adminApi.listDnc(q || undefined);
      setEntries(data);
    } catch {
      toast.error("Failed to load DNC list");
    } finally {
      setLoading(false);
    }
  }, [q]);

  useEffect(() => { load(); }, [load]);

  async function handleRemove(id: string, phone: string) {
    if (!confirm(`Remove ${phone} from DNC list?`)) return;
    try {
      await adminApi.removeDnc(id);
      toast.success("Removed from DNC list");
      load();
    } catch {
      toast.error("Failed to remove entry");
    }
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <PhoneOff className="h-6 w-6 text-destructive" />
            Do Not Call List
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Numbers on this list will be skipped automatically in all campaigns.
          </p>
        </div>
        <Button className="bg-gradient-primary text-white" onClick={() => setShowAdd(true)}>
          <Plus className="h-4 w-4" /> Add Number
        </Button>
      </div>

      {/* Info banner */}
      <div className="flex items-start gap-3 rounded-xl border border-primary/20 bg-primary/5 px-4 py-3 text-sm">
        <Shield className="h-4 w-4 text-primary mt-0.5 shrink-0" />
        <div>
          <span className="font-medium text-foreground">TRAI Compliance</span>
          <span className="text-muted-foreground ml-1">— Numbers added here are blocked org-wide. The system also checks India's national DNC registry automatically.</span>
        </div>
      </div>

      {/* Search + table */}
      <div className="rounded-xl bg-card border border-border overflow-hidden">
        <div className="px-4 py-3 border-b border-border/60 flex items-center gap-3">
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by number…"
              className="pl-9"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <span className="text-xs text-muted-foreground">{entries.length} entries</span>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : entries.length === 0 ? (
          <div className="py-16 text-center">
            <PhoneOff className="h-10 w-10 mx-auto text-muted-foreground/30 mb-3" />
            <p className="text-muted-foreground text-sm">No DNC entries yet</p>
            <p className="text-muted-foreground text-xs mt-1">Numbers customers opt out of will appear here automatically.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground bg-surface-2/40">
                  <th className="px-4 py-2.5 font-medium">Phone Number</th>
                  <th className="px-4 py-2.5 font-medium">Reason</th>
                  <th className="px-4 py-2.5 font-medium">Notes</th>
                  <th className="px-4 py-2.5 font-medium">Added</th>
                  <th className="px-4 py-2.5 font-medium text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id} className="border-t border-border/60 hover:bg-surface-2/30">
                    <td className="px-4 py-3 font-mono text-xs">{e.phone_number}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-2 py-0.5 rounded-full bg-destructive/10 text-destructive border border-destructive/20">
                        {e.reason.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{e.notes || "—"}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                      {new Date(e.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-destructive hover:text-destructive"
                        onClick={() => handleRemove(e.id, e.phone_number)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add dialog */}
      {showAdd && <AddDncDialog onClose={() => setShowAdd(false)} onAdded={load} />}
    </div>
  );
}

function AddDncDialog({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [phone, setPhone] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleAdd() {
    if (!phone.trim()) { toast.error("Phone number is required"); return; }
    setSaving(true);
    try {
      await adminApi.addDnc({ phone_number: phone.trim(), notes: notes.trim() || undefined });
      toast.success("Number added to DNC list");
      onAdded();
      onClose();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to add number");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <PhoneOff className="h-4 w-4 text-destructive" /> Add to DNC List
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-1">
          <div className="space-y-1.5">
            <Label>Phone Number *</Label>
            <Input
              placeholder="+91 98765 43210"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">Enter with country code (+91 for India) or plain 10-digit number</p>
          </div>
          <div className="space-y-1.5">
            <Label>Reason / Notes <span className="text-muted-foreground text-xs">(optional)</span></Label>
            <Input
              placeholder="e.g. Customer requested removal"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button className="bg-destructive text-white" onClick={handleAdd} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Add to DNC"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
