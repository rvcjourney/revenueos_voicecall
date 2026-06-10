import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, useEffect, useCallback } from "react";
import { sipTrunksApi, adminApi, type SipTrunkOut, type SipTrunkAssignment, type AdminUserOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { Phone, Plus, Trash2, Users, Loader2, Edit2, UserPlus, UserMinus, Star } from "lucide-react";

export const Route = createFileRoute("/_authed/admin/phone-numbers")({
  head: () => ({ meta: [{ title: "Phone Numbers — MOTMVoice" }] }),
  component: PhoneNumbersPage,
});

function PhoneNumbersPage() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();

  const [trunks, setTrunks]       = useState<SipTrunkOut[]>([]);
  const [loading, setLoading]     = useState(true);
  const [users, setUsers]         = useState<AdminUserOut[]>([]);

  // Dialogs
  const [showAdd, setShowAdd]           = useState(false);
  const [editTarget, setEditTarget]     = useState<SipTrunkOut | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<SipTrunkOut | null>(null);
  const [assignTarget, setAssignTarget] = useState<SipTrunkOut | null>(null);
  const [assignments, setAssignments]   = useState<SipTrunkAssignment[]>([]);
  const [assignsLoading, setAssignsLoading] = useState(false);

  useEffect(() => {
    if (!isAdmin) navigate({ to: "/dashboard" });
  }, [isAdmin, navigate]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data: t }, { data: u }] = await Promise.all([
        sipTrunksApi.list(),
        adminApi.listUsers(),
      ]);
      setTrunks(t);
      setUsers(u);
    } catch {
      toast.error("Failed to load phone numbers");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function openAssignments(trunk: SipTrunkOut) {
    setAssignTarget(trunk);
    setAssignsLoading(true);
    try {
      const { data } = await sipTrunksApi.getAssignments(trunk.id);
      setAssignments(data);
    } catch {
      toast.error("Failed to load assignments");
    } finally {
      setAssignsLoading(false);
    }
  }

  async function handleUnassign(userId: string) {
    if (!assignTarget) return;
    try {
      await sipTrunksApi.unassign(assignTarget.id, userId);
      setAssignments((prev) => prev.filter((a) => a.user_id !== userId));
      toast.success("Assignment removed");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to remove assignment");
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      await sipTrunksApi.delete(deleteTarget.id);
      toast.success("Phone number deleted");
      setDeleteTarget(null);
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to delete");
    }
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Phone className="h-6 w-6 text-primary" />
            Phone Numbers
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage SIP trunks and assign phone numbers to team members
          </p>
        </div>
        <Button className="bg-gradient-primary text-white" onClick={() => setShowAdd(true)}>
          <Plus className="h-4 w-4" /> Add Phone Number
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground gap-2">
          <Loader2 className="h-5 w-5 animate-spin" /> Loading…
        </div>
      ) : trunks.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-border bg-card">
          <Phone className="h-12 w-12 mx-auto mb-3 text-muted-foreground opacity-40" />
          <p className="font-medium">No phone numbers yet</p>
          <p className="text-sm text-muted-foreground mt-1">Add a SIP trunk to start making calls</p>
          <Button className="mt-4 bg-gradient-primary text-white" onClick={() => setShowAdd(true)}>
            <Plus className="h-4 w-4" /> Add Phone Number
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {trunks.map((trunk) => (
            <div key={trunk.id} className="rounded-xl bg-card border border-border p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-base font-bold">{trunk.caller_id}</span>
                    {trunk.is_default && (
                      <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-primary/15 text-primary font-medium">
                        <Star className="h-3 w-3" /> Default
                      </span>
                    )}
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      trunk.is_active
                        ? "bg-success/15 text-success"
                        : "bg-surface-3 text-muted-foreground"
                    }`}>
                      {trunk.is_active ? "Active" : "Inactive"}
                    </span>
                  </div>
                  <div className="text-sm font-medium mt-0.5">{trunk.name}</div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {trunk.sip_domain} · {trunk.transport.toUpperCase()}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Button
                    variant="outline" size="sm"
                    onClick={() => openAssignments(trunk)}
                    className="gap-1.5"
                  >
                    <Users className="h-3.5 w-3.5" /> Assign
                  </Button>
                  <Button
                    variant="outline" size="sm"
                    onClick={() => setEditTarget(trunk)}
                  >
                    <Edit2 className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="outline" size="sm"
                    className="text-destructive hover:text-destructive hover:border-destructive"
                    onClick={() => setDeleteTarget(trunk)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Trunk Dialog */}
      <AddTrunkDialog
        open={showAdd}
        onClose={() => setShowAdd(false)}
        onSaved={() => { setShowAdd(false); load(); }}
      />

      {/* Edit Trunk Dialog */}
      {editTarget && (
        <EditTrunkDialog
          trunk={editTarget}
          onClose={() => setEditTarget(null)}
          onSaved={() => { setEditTarget(null); load(); }}
        />
      )}

      {/* Delete Confirm */}
      <AlertDialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete phone number?</AlertDialogTitle>
            <AlertDialogDescription>
              "{deleteTarget?.name} ({deleteTarget?.caller_id})" will be deleted and all user assignments removed.
              Running campaigns using this number will fail.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-white hover:bg-destructive/90">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Assign Users Dialog */}
      {assignTarget && (
        <Dialog open={!!assignTarget} onOpenChange={() => setAssignTarget(null)}>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle>
                Assign "{assignTarget.name}" ({assignTarget.caller_id})
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <AssignUserSection
                trunkId={assignTarget.id}
                users={users}
                assignments={assignments}
                loading={assignsLoading}
                onAssigned={(a) => setAssignments((prev) => [...prev, a])}
                onUnassign={handleUnassign}
              />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setAssignTarget(null)}>Close</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

// ── Add Trunk Dialog ──────────────────────────────────────────────────────────

function AddTrunkDialog({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    name: "", livekit_trunk_id: "", sip_domain: "",
    sip_username: "", sip_password: "", caller_id: "",
    transport: "tcp", is_default: false,
  });
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (!form.name || !form.livekit_trunk_id || !form.sip_domain || !form.caller_id) {
      toast.error("Name, LiveKit Trunk ID, SIP Domain, and Caller ID are required");
      return;
    }
    setSaving(true);
    try {
      await sipTrunksApi.create(form);
      toast.success("Phone number added");
      onSaved();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to add phone number");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add Phone Number</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5 col-span-2">
              <Label>Display Name *</Label>
              <Input placeholder="e.g. Sales India" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="space-y-1.5 col-span-2">
              <Label>Caller ID (Phone Number) *</Label>
              <Input placeholder="+918888888888" value={form.caller_id} onChange={(e) => setForm({ ...form, caller_id: e.target.value })} />
            </div>
            <div className="space-y-1.5 col-span-2">
              <Label>LiveKit Trunk ID *</Label>
              <Input placeholder="ST_xxxxxxxxxxxx" value={form.livekit_trunk_id} onChange={(e) => setForm({ ...form, livekit_trunk_id: e.target.value })} />
              <p className="text-xs text-muted-foreground">From LiveKit dashboard → SIP → Outbound trunks</p>
            </div>
            <div className="space-y-1.5">
              <Label>SIP Domain *</Label>
              <Input placeholder="sip.provider.com" value={form.sip_domain} onChange={(e) => setForm({ ...form, sip_domain: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label>Transport</Label>
              <Select value={form.transport} onValueChange={(v) => setForm({ ...form, transport: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="tcp">TCP</SelectItem>
                  <SelectItem value="udp">UDP</SelectItem>
                  <SelectItem value="tls">TLS</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>SIP Username</Label>
              <Input value={form.sip_username} onChange={(e) => setForm({ ...form, sip_username: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label>SIP Password</Label>
              <Input type="password" value={form.sip_password} onChange={(e) => setForm({ ...form, sip_password: e.target.value })} />
            </div>
            <div className="col-span-2 flex items-center gap-2 pt-1">
              <input
                type="checkbox" id="is_default"
                checked={form.is_default}
                onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
                className="h-4 w-4 accent-primary"
              />
              <Label htmlFor="is_default" className="cursor-pointer font-normal">Set as org default number</Label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button className="bg-gradient-primary text-white" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Edit Trunk Dialog ─────────────────────────────────────────────────────────

function EditTrunkDialog({ trunk, onClose, onSaved }: { trunk: SipTrunkOut; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    name: trunk.name,
    caller_id: trunk.caller_id,
    is_default: trunk.is_default,
    is_active: trunk.is_active,
  });
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      await sipTrunksApi.update(trunk.id, form);
      toast.success("Phone number updated");
      onSaved();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to update");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Edit Phone Number</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-1.5">
            <Label>Display Name</Label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="space-y-1.5">
            <Label>Caller ID</Label>
            <Input value={form.caller_id} onChange={(e) => setForm({ ...form, caller_id: e.target.value })} />
          </div>
          <div className="flex items-center gap-4 pt-1">
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <input
                type="checkbox" checked={form.is_default}
                onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
                className="h-4 w-4 accent-primary"
              />
              Set as default
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <input
                type="checkbox" checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                className="h-4 w-4 accent-primary"
              />
              Active
            </label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button className="bg-gradient-primary text-white" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Assign User Section ───────────────────────────────────────────────────────

function AssignUserSection({
  trunkId, users, assignments, loading, onAssigned, onUnassign,
}: {
  trunkId: string;
  users: AdminUserOut[];
  assignments: SipTrunkAssignment[];
  loading: boolean;
  onAssigned: (a: SipTrunkAssignment) => void;
  onUnassign: (userId: string) => void;
}) {
  const [selectedUserId, setSelectedUserId] = useState("");
  const [assigning, setAssigning]           = useState(false);

  const assignedIds = new Set(assignments.map((a) => a.user_id));
  const unassignedUsers = users.filter((u) => !assignedIds.has(u.id) && u.is_active);

  async function handleAssign() {
    if (!selectedUserId) return;
    setAssigning(true);
    try {
      await sipTrunksApi.assign(trunkId, selectedUserId);
      const user = users.find((u) => u.id === selectedUserId);
      if (user) {
        onAssigned({
          user_id: user.id,
          full_name: user.full_name,
          email: user.email,
          assigned_at: new Date().toISOString(),
        });
      }
      setSelectedUserId("");
      toast.success("Phone number assigned");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to assign");
    } finally {
      setAssigning(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* Assign to user */}
      <div>
        <Label className="text-xs text-muted-foreground uppercase tracking-wide mb-2 block">
          Assign to user
        </Label>
        <div className="flex gap-2">
          <Select value={selectedUserId} onValueChange={setSelectedUserId}>
            <SelectTrigger className="flex-1">
              <SelectValue placeholder="Select a team member…" />
            </SelectTrigger>
            <SelectContent>
              {unassignedUsers.length === 0 ? (
                <div className="px-3 py-2 text-sm text-muted-foreground">All users already assigned</div>
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
            onClick={handleAssign}
            disabled={!selectedUserId || assigning}
          >
            {assigning ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* Currently assigned */}
      <div>
        <Label className="text-xs text-muted-foreground uppercase tracking-wide mb-2 block">
          Currently assigned ({assignments.length})
        </Label>
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </div>
        ) : assignments.length === 0 ? (
          <p className="text-sm text-muted-foreground">No users assigned yet.</p>
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
                  title="Remove assignment"
                >
                  <UserMinus className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
