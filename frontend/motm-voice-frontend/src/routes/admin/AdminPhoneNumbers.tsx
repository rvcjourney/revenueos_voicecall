import { useState } from "react";
import { toast } from "sonner";
import { Check, Loader2, Phone, PhoneCall, Plus, Trash2, UserMinus, UserPlus } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminUsers, useSipTrunks, useTrunkAssignments } from "@/lib/hooks";
import { sipTrunksApi, apiErrorMessage } from "@/lib/api";
import { initials } from "@/lib/utils";
import type { SipTrunk } from "@/lib/types";

export default function AdminPhoneNumbers() {
  const trunks = useSipTrunks();
  const [connectOpen, setConnectOpen] = useState(false);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Phone Numbers"
        description="Assign organisation phone numbers to team members"
        actions={
          <Dialog open={connectOpen} onOpenChange={setConnectOpen}>
            <DialogTrigger asChild>
              <Button variant="gradient"><Plus className="h-4 w-4" /> Connect number</Button>
            </DialogTrigger>
            <ConnectVobizDialog onDone={() => setConnectOpen(false)} />
          </Dialog>
        }
      />

      {trunks.isError ? (
        <ErrorBanner error={trunks.error} onRetry={() => trunks.refetch()} />
      ) : trunks.isLoading ? (
        <div className="space-y-4">{[1, 2].map((i) => <Skeleton key={i} className="h-56 w-full" />)}</div>
      ) : trunks.data && trunks.data.length > 0 ? (
        <div className="space-y-4">
          {trunks.data.map((t) => <TrunkCard key={t.id} trunk={t} />)}
        </div>
      ) : (
        <EmptyState
          icon={Phone}
          title="No phone numbers connected"
          description="Connect a SIP trunk so your AI agents can start making real calls."
          action={<Button variant="gradient" onClick={() => setConnectOpen(true)}>Connect number</Button>}
        />
      )}
    </div>
  );
}

function TrunkCard({ trunk }: { trunk: SipTrunk }) {
  const users = useAdminUsers();
  const assignments = useTrunkAssignments(trunk.id);
  const [selectedUser, setSelectedUser] = useState("");
  const [testing, setTesting] = useState(false);
  const qc = useQueryClient();

  async function grant() {
    if (!selectedUser) return;
    try {
      await sipTrunksApi.assign(trunk.id, selectedUser);
      qc.invalidateQueries({ queryKey: ["trunk-assignments", trunk.id] });
      setSelectedUser("");
      toast.success("Access granted");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't grant access"));
    }
  }

  async function revoke(userId: string) {
    try {
      await sipTrunksApi.unassign(trunk.id, userId);
      qc.invalidateQueries({ queryKey: ["trunk-assignments", trunk.id] });
      toast.success("Access removed");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't remove access"));
    }
  }

  async function runTest() {
    setTesting(true);
    try {
      const res = await sipTrunksApi.test(trunk.id);
      qc.invalidateQueries({ queryKey: ["sip-trunks"] });
      toast[res.data.is_active ? "success" : "error"](res.data.is_active ? "Test call succeeded" : "Test call failed");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't run test call"));
    } finally {
      setTesting(false);
    }
  }

  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!confirm(`Delete ${trunk.caller_id}? Campaigns or agents still using this number will stop being able to call.`)) return;
    setDeleting(true);
    try {
      await sipTrunksApi.remove(trunk.id);
      qc.invalidateQueries({ queryKey: ["sip-trunks"] });
      qc.invalidateQueries({ queryKey: ["my-trunks"] });
      toast.success("Phone number deleted");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't delete phone number"));
    } finally {
      setDeleting(false);
    }
  }

  const assignedIds = new Set((assignments.data ?? []).map((a) => a.user_id));
  const available = (users.data ?? []).filter((u) => !assignedIds.has(u.id));
  const accent = trunk.is_active ? "var(--success)" : "var(--muted-foreground)";

  return (
    <div className="relative overflow-hidden rounded-2xl border border-border bg-card shadow-[var(--shadow-card)] transition-all duration-200 hover:shadow-[var(--shadow-elevated)]">
      <span className="absolute inset-x-0 top-0 h-1.5" style={{ backgroundColor: accent }} />
      <div className="space-y-5 p-5 pt-6">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
          <div className="flex items-start gap-3.5">
            <span
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl"
              style={{ backgroundColor: `${accent}1f`, color: accent }}
            >
              <Phone className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <p className="font-heading text-xl font-semibold tracking-tight">{trunk.caller_id}</p>
              <p className="text-sm text-muted-foreground">{trunk.name}</p>
              <p className="mt-0.5 font-mono text-xs text-muted-foreground/80">
                {trunk.sip_domain} · {trunk.transport.toUpperCase()}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={trunk.is_active ? "success" : "destructive"}>
              {trunk.is_active ? <Check className="h-3 w-3" /> : null} {trunk.is_active ? "Active" : "Inactive"}
            </Badge>
            <Button variant="outline" size="sm" onClick={runTest} disabled={testing}>
              {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PhoneCall className="h-3.5 w-3.5" />}
              Test call
            </Button>
            <Button variant="outline" size="sm" onClick={handleDelete} disabled={deleting}>
              {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5 text-destructive" />}
            </Button>
          </div>
        </div>

        <div className="space-y-4 rounded-xl border border-border/60 bg-muted/30 p-4">
          <p className="flex items-center gap-2 text-sm font-semibold">
            <UserPlus className="h-4 w-4 text-muted-foreground" /> User Access
          </p>
          <div className="flex gap-2">
            <Select value={selectedUser} onValueChange={setSelectedUser}>
              <SelectTrigger className="flex-1 bg-card"><SelectValue placeholder="Select a team member..." /></SelectTrigger>
              <SelectContent>
                {available.map((u) => <SelectItem key={u.id} value={u.id}>{u.full_name} ({u.email})</SelectItem>)}
              </SelectContent>
            </Select>
            <Button variant="gradient" onClick={grant} disabled={!selectedUser}>
              <UserPlus className="h-4 w-4" />
            </Button>
          </div>

          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Currently assigned ({assignments.data?.length ?? 0})
            </p>
            {assignments.isLoading ? (
              <Skeleton className="h-10 w-full" />
            ) : assignments.data && assignments.data.length > 0 ? (
              <div className="space-y-2">
                {assignments.data.map((a) => (
                  <div
                    key={a.user_id}
                    className="flex items-center justify-between rounded-lg border border-border bg-card px-3 py-2.5"
                  >
                    <div className="flex min-w-0 items-center gap-2.5">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[image:var(--gradient-primary)] text-[11px] font-semibold text-primary-foreground">
                        {initials(a.full_name)}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{a.full_name}</p>
                        <p className="truncate text-xs text-muted-foreground">{a.email}</p>
                      </div>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => revoke(a.user_id)}>
                      <UserMinus className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rounded-lg border border-dashed border-border px-3 py-3 text-sm text-muted-foreground">
                No one has access to this number yet.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ConnectVobizDialog({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({ auth_id: "", auth_token: "", did: "" });
  const [trunkId, setTrunkId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const qc = useQueryClient();

  async function handleConnect() {
    if (!form.auth_id || !form.auth_token || !form.did) {
      toast.error("Fill in all fields");
      return;
    }
    setLoading(true);
    try {
      const res = await sipTrunksApi.connectVobiz(form);
      setTrunkId(res.data.trunk_id);
      setStep(1);
      qc.invalidateQueries({ queryKey: ["sip-trunks"] });
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't connect number"));
    } finally {
      setLoading(false);
    }
  }

  async function handleTest() {
    if (!trunkId) return;
    setLoading(true);
    try {
      const res = await sipTrunksApi.test(trunkId);
      qc.invalidateQueries({ queryKey: ["sip-trunks"] });
      if (res.data.is_active) {
        toast.success("Number verified and ready to call!");
        onDone();
      } else {
        toast.error("Test call failed — check your credentials and try again.");
      }
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't run test call"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Connect your number</DialogTitle>
      </DialogHeader>
      <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
        <StepDot active={step >= 0} label="Connect" />
        <div className="h-px flex-1 bg-border" />
        <StepDot active={step >= 1} label="Verify" />
      </div>

      {step === 0 && (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Vobiz Auth ID</Label>
            <Input value={form.auth_id} onChange={(e) => setForm((f) => ({ ...f, auth_id: e.target.value }))} />
          </div>
          <div className="space-y-1.5">
            <Label>Vobiz Auth Token</Label>
            <Input type="password" value={form.auth_token} onChange={(e) => setForm((f) => ({ ...f, auth_token: e.target.value }))} />
          </div>
          <div className="space-y-1.5">
            <Label>Phone number (DID)</Label>
            <Input placeholder="+91XXXXXXXXXX" value={form.did} onChange={(e) => setForm((f) => ({ ...f, did: e.target.value }))} />
          </div>
        </div>
      )}

      {step === 1 && (
        <div className="space-y-3 text-center">
          <p className="text-sm text-muted-foreground">
            Your number <span className="font-medium text-foreground">{form.did}</span> is connected. Run a test call to confirm it's ready.
          </p>
        </div>
      )}

      <DialogFooter>
        {step === 0 ? (
          <Button variant="gradient" onClick={handleConnect} disabled={loading}>
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            Connect
          </Button>
        ) : (
          <Button variant="gradient" onClick={handleTest} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <PhoneCall className="h-4 w-4" />}
            Run test call
          </Button>
        )}
      </DialogFooter>
    </DialogContent>
  );
}

function StepDot({ active, label }: { active: boolean; label: string }) {
  return (
    <span className={`flex items-center gap-1.5 ${active ? "text-primary" : ""}`}>
      <span className={`h-2 w-2 rounded-full ${active ? "bg-primary" : "bg-border"}`} />
      {label}
    </span>
  );
}
