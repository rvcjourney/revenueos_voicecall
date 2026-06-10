import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, useEffect, useCallback } from "react";
import { sipTrunksApi, adminApi, type SipTrunkOut, type SipTrunkAssignment, type AdminUserOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Phone, Users, Loader2, UserPlus, UserMinus, Star, CheckCircle2 } from "lucide-react";

export const Route = createFileRoute("/_authed/admin/phone-numbers")({
  head: () => ({ meta: [{ title: "Phone Numbers — MOTMVoice" }] }),
  component: PhoneNumbersPage,
});

function PhoneNumbersPage() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();

  const [trunks, setTrunks]   = useState<SipTrunkOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [initializing, setInit] = useState(false);
  const [users, setUsers]     = useState<AdminUserOut[]>([]);
  const [assignments, setAssignments] = useState<Record<string, SipTrunkAssignment[]>>({});

  useEffect(() => {
    if (!isAdmin) navigate({ to: "/dashboard" });
  }, [isAdmin, navigate]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data: ts }, { data: u }] = await Promise.all([
        sipTrunksApi.list(),
        adminApi.listUsers(),
      ]);
      setUsers(u);
      setTrunks(ts);
      if (ts.length > 0) {
        const results = await Promise.all(ts.map((t) => sipTrunksApi.getAssignments(t.id)));
        const map: Record<string, SipTrunkAssignment[]> = {};
        ts.forEach((t, i) => { map[t.id] = results[i].data; });
        setAssignments(map);
      }
    } catch {
      toast.error("Failed to load phone numbers");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleInit() {
    setInit(true);
    try {
      await sipTrunksApi.initDefault();
      await load();
      toast.success("Phone numbers activated");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to activate");
    } finally {
      setInit(false);
    }
  }

  async function handleAssign(trunkId: string, userId: string) {
    try {
      await sipTrunksApi.assign(trunkId, userId);
      const user = users.find((u) => u.id === userId);
      if (user) {
        setAssignments((prev) => ({
          ...prev,
          [trunkId]: [
            ...(prev[trunkId] ?? []),
            { user_id: user.id, full_name: user.full_name, email: user.email, assigned_at: new Date().toISOString() },
          ],
        }));
      }
      toast.success("Access granted");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to assign");
    }
  }

  async function handleUnassign(trunkId: string, userId: string) {
    try {
      await sipTrunksApi.unassign(trunkId, userId);
      setAssignments((prev) => ({
        ...prev,
        [trunkId]: (prev[trunkId] ?? []).filter((a) => a.user_id !== userId),
      }));
      toast.success("Access removed");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to remove access");
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Phone className="h-6 w-6 text-primary" />
          Phone Numbers
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Assign organisation phone numbers to team members
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground gap-2">
          <Loader2 className="h-5 w-5 animate-spin" /> Loading…
        </div>
      ) : trunks.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-8 text-center space-y-4">
          <Phone className="h-12 w-12 mx-auto text-muted-foreground opacity-40" />
          <div>
            <p className="font-semibold text-lg font-mono">+91 80654 80087</p>
            <p className="text-sm text-muted-foreground mt-1">Vobiz SIP Trunks (not yet activated)</p>
          </div>
          <Button
            className="bg-gradient-primary text-white"
            onClick={handleInit}
            disabled={initializing}
          >
            {initializing
              ? <><Loader2 className="h-4 w-4 animate-spin" /> Activating…</>
              : "Activate Phone Numbers"}
          </Button>
          <p className="text-xs text-muted-foreground">
            This registers all configured SIP trunks so you can assign them to users.
          </p>
        </div>
      ) : (
        <div className="space-y-8">
          {trunks.map((trunk) => (
            <TrunkSection
              key={trunk.id}
              trunk={trunk}
              users={users}
              assignments={assignments[trunk.id] ?? []}
              onAssign={(userId) => handleAssign(trunk.id, userId)}
              onUnassign={(userId) => handleUnassign(trunk.id, userId)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Single trunk card + assignment section ────────────────────────────────────

function TrunkSection({
  trunk, users, assignments, onAssign, onUnassign,
}: {
  trunk: SipTrunkOut;
  users: AdminUserOut[];
  assignments: SipTrunkAssignment[];
  onAssign: (userId: string) => void;
  onUnassign: (userId: string) => void;
}) {
  return (
    <div className="space-y-4">
      {/* Phone number card — read-only */}
      <div className="rounded-xl bg-card border border-border p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-xl font-bold">{trunk.caller_id}</span>
              {trunk.is_default && (
                <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-primary/15 text-primary font-medium">
                  <Star className="h-3 w-3" /> Default
                </span>
              )}
            </div>
            <div className="text-sm font-medium mt-0.5 text-muted-foreground">{trunk.name}</div>
            <div className="text-xs text-muted-foreground mt-1">
              {trunk.sip_domain} · {trunk.transport.toUpperCase()}
            </div>
          </div>
          <span className="flex items-center gap-1.5 text-xs font-medium text-success shrink-0 mt-1">
            <CheckCircle2 className="h-4 w-4" /> Active
          </span>
        </div>
      </div>

      {/* User assignment section */}
      <div className="rounded-xl bg-card border border-border p-5 space-y-5">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold">User Access</h2>
        </div>

        <AssignRow
          users={users}
          assignments={assignments}
          onAssign={onAssign}
        />

        <div>
          <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium mb-2">
            Currently assigned ({assignments.length})
          </p>
          {assignments.length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">
              No users have access yet. Select a user above to grant access.
            </p>
          ) : (
            <div className="space-y-2">
              {assignments.map((a) => (
                <div key={a.user_id} className="flex items-center justify-between p-3 rounded-lg bg-surface-2/60 border border-border">
                  <div>
                    <div className="text-sm font-medium">{a.full_name}</div>
                    <div className="text-xs text-muted-foreground">{a.email}</div>
                  </div>
                  <button
                    onClick={() => onUnassign(a.user_id)}
                    className="h-7 w-7 grid place-items-center rounded-md border border-border hover:border-destructive hover:text-destructive text-muted-foreground transition-colors"
                    title="Remove access"
                  >
                    <UserMinus className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Assign row ────────────────────────────────────────────────────────────────

function AssignRow({
  users, assignments, onAssign,
}: {
  users: AdminUserOut[];
  assignments: SipTrunkAssignment[];
  onAssign: (userId: string) => void;
}) {
  const [selected, setSelected] = useState("");
  const [busy, setBusy]         = useState(false);

  const assignedIds     = new Set(assignments.map((a) => a.user_id));
  const unassignedUsers = users.filter((u) => !assignedIds.has(u.id) && u.is_active);

  async function handleGrant() {
    if (!selected) return;
    setBusy(true);
    await onAssign(selected);
    setSelected("");
    setBusy(false);
  }

  return (
    <div>
      <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium mb-2">
        Grant access to user
      </p>
      <div className="flex gap-2">
        <Select value={selected} onValueChange={setSelected}>
          <SelectTrigger className="flex-1">
            <SelectValue placeholder="Select a team member…" />
          </SelectTrigger>
          <SelectContent>
            {unassignedUsers.length === 0 ? (
              <div className="px-3 py-2 text-sm text-muted-foreground">All active users already have access</div>
            ) : (
              unassignedUsers.map((u) => (
                <SelectItem key={u.id} value={u.id}>
                  {u.full_name} — {u.email}
                </SelectItem>
              ))
            )}
          </SelectContent>
        </Select>
        <Button
          className="bg-gradient-primary text-white shrink-0"
          onClick={handleGrant}
          disabled={!selected || busy}
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  );
}
