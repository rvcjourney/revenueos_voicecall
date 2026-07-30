import { useState } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Search, ShieldBan, Trash2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { useDncList } from "@/lib/hooks";
import { adminApi, apiErrorMessage } from "@/lib/api";
import { formatDate, titleCase } from "@/lib/utils";

export default function AdminDnc() {
  const [search, setSearch] = useState("");
  const dnc = useDncList(search || undefined);
  const [addOpen, setAddOpen] = useState(false);
  const qc = useQueryClient();

  async function remove(id: string) {
    try {
      await adminApi.removeDnc(id);
      qc.invalidateQueries({ queryKey: ["dnc"] });
      toast.success("Removed from DNC list");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't remove entry"));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Do Not Call List"
        description="Numbers on this list will be skipped automatically in all campaigns."
        actions={
          <Dialog open={addOpen} onOpenChange={setAddOpen}>
            <DialogTrigger asChild>
              <Button variant="gradient"><Plus className="h-4 w-4" /> Add Number</Button>
            </DialogTrigger>
            <AddDncDialog onDone={() => setAddOpen(false)} />
          </Dialog>
        }
      />

      <div className="flex items-start gap-3 rounded-xl border border-info/30 bg-info/10 p-4 text-sm">
        <ShieldBan className="mt-0.5 h-4 w-4 shrink-0 text-info" />
        <p>
          <span className="font-medium text-info">TRAI Compliance</span> — Numbers added here are blocked org-wide. The
          system also checks India's national DNC registry automatically.
        </p>
      </div>

      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input placeholder="Search by number..." value={search} onChange={(e) => setSearch(e.target.value)} className="max-w-sm pl-8" />
      </div>

      {dnc.isError ? (
        <ErrorBanner error={dnc.error} onRetry={() => dnc.refetch()} />
      ) : dnc.isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : dnc.data && dnc.data.length > 0 ? (
        <Card>
          <CardContent className="divide-y divide-border/60 pt-6">
            {dnc.data.map((entry) => (
              <div key={entry.id} className="flex items-center justify-between py-3 first:pt-0 last:pb-0">
                <div>
                  <p className="font-mono text-sm">{entry.phone_number}</p>
                  <p className="text-xs text-muted-foreground">
                    {titleCase(entry.reason)} · Added {formatDate(entry.created_at)}
                    {entry.notes && ` · ${entry.notes}`}
                  </p>
                </div>
                <Button variant="ghost" size="sm" onClick={() => remove(entry.id)}>
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : (
        <EmptyState
          icon={ShieldBan}
          title="No DNC entries yet"
          description="Numbers customers opt out of will appear here automatically."
        />
      )}
    </div>
  );
}

function AddDncDialog({ onDone }: { onDone: () => void }) {
  const [phone, setPhone] = useState("+91");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const qc = useQueryClient();

  async function handleSubmit() {
    if (!phone.trim()) {
      toast.error("Enter a phone number");
      return;
    }
    setSubmitting(true);
    try {
      await adminApi.addDnc({ phone_number: phone, notes: notes || undefined });
      qc.invalidateQueries({ queryKey: ["dnc"] });
      toast.success("Number added to DNC list");
      onDone();
      setPhone("+91");
      setNotes("");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't add number"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <DialogContent>
      <DialogHeader><DialogTitle>Add to Do Not Call list</DialogTitle></DialogHeader>
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label>Phone number</Label>
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91 98765 43210" />
        </div>
        <div className="space-y-1.5">
          <Label>Notes (optional)</Label>
          <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Why is this number being blocked?" />
        </div>
      </div>
      <DialogFooter>
        <Button variant="gradient" onClick={handleSubmit} disabled={submitting}>
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          Add number
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
