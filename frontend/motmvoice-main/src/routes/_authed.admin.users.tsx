import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, useEffect } from "react";
import { adminApi, type AdminUserOut, type OrgInfo, type AgentAccessRequestOut, type AgentCreationRequestAdminOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import {
  Users, Plus, Shield, UserCheck, UserX, Trash2, Copy, Loader2,
  RefreshCw, Key, Bot, CheckCircle, XCircle, Clock,
} from "lucide-react";

export const Route = createFileRoute("/_authed/admin/users")({
  head: () => ({ meta: [{ title: "Team — MOTMVoice" }] }),
  component: AdminUsersPage,
});

function AdminUsersPage() {
  const { isAdmin, user: me } = useAuth();
  const navigate = useNavigate();

  const [users, setUsers]                   = useState<AdminUserOut[]>([]);
  const [org, setOrg]                       = useState<OrgInfo | null>(null);
  const [agentRequests, setAgentReqs]       = useState<AgentAccessRequestOut[]>([]);
  const [creationRequests, setCreationReqs] = useState<AgentCreationRequestAdminOut[]>([]);
  const [loading, setLoading]               = useState(true);
  const [showCreate, setShowCreate]         = useState(false);
  const [expandedReq, setExpandedReq]       = useState<string | null>(null);

  // Redirect members away
  useEffect(() => {
    if (!isAdmin) navigate({ to: "/dashboard" });
  }, [isAdmin, navigate]);

  async function load() {
    setLoading(true);
    try {
      const [usersRes, orgRes] = await Promise.all([
        adminApi.listUsers(),
        adminApi.getOrg(),
      ]);
      setUsers(usersRes.data);
      setOrg(orgRes.data);
    } catch {
      toast.error("Failed to load team data");
    } finally {
      setLoading(false);
    }
    // Load agent access + creation requests (fail silently if table missing)
    try {
      const [accessRes, creationRes] = await Promise.all([
        adminApi.listAgentRequests(),
        adminApi.listAgentCreationRequests(),
      ]);
      setAgentReqs(accessRes.data);
      setCreationReqs(creationRes.data);
    } catch {
      // silently ignore if migrations not yet run
    }
  }

  async function handleReview(id: string) {
    try {
      await adminApi.reviewAgentCreationRequest(id);
      toast.success("Marked as reviewed");
      load();
    } catch { toast.error("Failed to update"); }
  }

  useEffect(() => { load(); }, []);

  async function handleApprove(req: AgentAccessRequestOut) {
    try {
      await adminApi.approveAgentRequest(req.id);
      toast.success(`${req.user_name} now has access to "${req.agent_name}"`);
      load();
    } catch { toast.error("Failed to approve"); }
  }

  async function handleReject(req: AgentAccessRequestOut) {
    try {
      await adminApi.rejectAgentRequest(req.id);
      toast.success("Request rejected");
      load();
    } catch { toast.error("Failed to reject"); }
  }

  async function toggleActive(u: AdminUserOut) {
    try {
      await adminApi.updateUser(u.id, { is_active: !u.is_active });
      toast.success(u.is_active ? "User deactivated" : "User activated");
      load();
    } catch {
      toast.error("Failed to update user");
    }
  }

  async function deleteUser(u: AdminUserOut) {
    if (!confirm(`Delete ${u.full_name}? This cannot be undone.`)) return;
    try {
      await adminApi.deleteUser(u.id);
      toast.success("User removed");
      load();
    } catch {
      toast.error("Failed to delete user");
    }
  }

  function copyInviteCode() {
    if (!org) return;
    navigator.clipboard.writeText(org.invite_code);
    toast.success("Invite code copied! Share with your team.");
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-[1200px]">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Users className="h-6 w-6" /> Team
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage your sales team members and their access
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button size="sm" className="bg-gradient-primary text-white" onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4" /> Add Member
          </Button>
        </div>
      </div>

      {/* Org invite code card */}
      {org && (
        <div className="rounded-xl bg-card border border-border p-5">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <Key className="h-4 w-4 text-primary" />
                <span className="font-semibold text-sm">Team Invite Code</span>
              </div>
              <p className="text-xs text-muted-foreground">
                Share this code with your team. They enter it on the{" "}
                <strong>Join Team</strong> page to create their account.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <code className="text-2xl font-mono font-bold tracking-widest text-primary px-4 py-2 rounded-lg border border-primary/30 bg-primary/5">
                {org.invite_code}
              </code>
              <Button variant="outline" size="sm" onClick={copyInviteCode}>
                <Copy className="h-4 w-4" /> Copy
              </Button>
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-border flex gap-6 text-xs text-muted-foreground">
            <span>Plan: <strong className="text-foreground capitalize">{org.plan_tier}</strong></span>
            <span>Quota: <strong className="text-foreground">{org.calls_used_this_period} / {org.monthly_call_quota} calls</strong></span>
          </div>
        </div>
      )}

      {/* Users table */}
      <div className="rounded-xl bg-card border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground bg-surface-2/40 border-b border-border">
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Email</th>
              <th className="px-4 py-3 font-medium">Role</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Last Login</th>
              <th className="px-4 py-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-t border-border/60 hover:bg-surface-2/30">
                <td className="px-4 py-3 font-medium">
                  {u.full_name}
                  {u.id === me?.id && (
                    <span className="ml-2 text-[10px] text-muted-foreground">(you)</span>
                  )}
                </td>
                <td className="px-4 py-3 text-muted-foreground text-xs font-mono">{u.email}</td>
                <td className="px-4 py-3">
                  {u.role === "admin" ? (
                    <Badge variant="outline" className="text-primary border-primary/40 text-[10px] gap-1">
                      <Shield className="h-2.5 w-2.5" /> Admin
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-muted-foreground text-[10px]">
                      Member
                    </Badge>
                  )}
                </td>
                <td className="px-4 py-3">
                  {u.is_active ? (
                    <span className="inline-flex items-center gap-1 text-xs text-green-400">
                      <span className="h-1.5 w-1.5 rounded-full bg-green-400 inline-block" /> Active
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs text-destructive">
                      <span className="h-1.5 w-1.5 rounded-full bg-destructive inline-block" /> Inactive
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-muted-foreground">
                  {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : "Never"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-1">
                    {u.id !== me?.id && (
                      <>
                        <Button
                          variant="ghost" size="sm"
                          className="h-7 text-xs"
                          title={u.is_active ? "Deactivate" : "Activate"}
                          onClick={() => toggleActive(u)}
                        >
                          {u.is_active
                            ? <UserX className="h-3.5 w-3.5 text-amber-400" />
                            : <UserCheck className="h-3.5 w-3.5 text-green-400" />}
                        </Button>
                        <Button
                          variant="ghost" size="sm"
                          className="h-7 text-xs"
                          title="Delete user"
                          onClick={() => deleteUser(u)}
                        >
                          <Trash2 className="h-3.5 w-3.5 text-destructive" />
                        </Button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && (
          <div className="p-12 text-center text-muted-foreground text-sm">
            No team members yet. Add one above.
          </div>
        )}
      </div>

      {/* Agent Access Requests */}
      <div className="rounded-xl bg-card border border-border overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2 font-semibold text-sm">
            <Bot className="h-4 w-4 text-primary" />
            Agent Access Requests
            {agentRequests.length > 0 && (
              <span className="ml-1 inline-flex items-center justify-center h-5 min-w-5 px-1.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">
                {agentRequests.length}
              </span>
            )}
          </div>
          <span className="text-xs text-muted-foreground">Pending approvals from your team</span>
        </div>

        {agentRequests.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            No pending access requests
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground bg-surface-2/40 border-b border-border">
                <th className="px-4 py-2 font-medium">Member</th>
                <th className="px-4 py-2 font-medium">Requested Agent</th>
                <th className="px-4 py-2 font-medium">Requested</th>
                <th className="px-4 py-2 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {agentRequests.map((r) => (
                <tr key={r.id} className="border-t border-border/60 hover:bg-surface-2/30">
                  <td className="px-4 py-3">
                    <div className="font-medium text-xs">{r.user_name}</div>
                    <div className="text-[11px] text-muted-foreground">{r.user_email}</div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="inline-flex items-center gap-1.5 text-xs font-medium text-primary">
                      <Bot className="h-3 w-3" /> {r.agent_name}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {new Date(r.created_at).toLocaleDateString()}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        size="sm" className="h-7 text-xs bg-green-500/15 text-green-400 border border-green-500/30 hover:bg-green-500/25"
                        variant="outline"
                        onClick={() => handleApprove(r)}
                      >
                        <CheckCircle className="h-3 w-3" /> Approve
                      </Button>
                      <Button
                        size="sm" variant="ghost" className="h-7 text-xs text-destructive hover:text-destructive"
                        onClick={() => handleReject(r)}
                      >
                        <XCircle className="h-3 w-3" /> Reject
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Agent Creation Requests */}
      <div className="rounded-xl bg-card border border-border overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2 font-semibold text-sm">
            <Bot className="h-4 w-4 text-primary" />
            New Agent Requests
            {creationRequests.length > 0 && (
              <span className="inline-flex items-center justify-center h-5 min-w-5 px-1.5 rounded-full text-[10px] font-bold bg-primary/20 text-primary border border-primary/30">
                {creationRequests.length}
              </span>
            )}
          </div>
          <span className="text-xs text-muted-foreground">Members requesting a new AI Agent to be created</span>
        </div>

        {creationRequests.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">No pending agent creation requests</div>
        ) : (
          <div className="divide-y divide-border">
            {creationRequests.map((r) => (
              <div key={r.id} className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-sm">{r.agent_name}</span>
                      <span className="text-xs text-muted-foreground">— {r.company_name}</span>
                      <span className="text-[10px] border border-border px-2 py-0.5 rounded text-muted-foreground">
                        {r.user_name} · {r.user_email}
                      </span>
                      <span className="text-[10px] text-muted-foreground">{new Date(r.created_at).toLocaleDateString()}</span>
                    </div>

                    {expandedReq === r.id && (
                      <div className="mt-3 space-y-2 text-xs bg-surface-2/50 rounded-lg p-3">
                        <div><span className="text-muted-foreground font-medium">What they sell:</span> <span>{r.product_service}</span></div>
                        <div><span className="text-muted-foreground font-medium">Target customers:</span> <span>{r.target_customers}</span></div>
                        <div><span className="text-muted-foreground font-medium">Key points:</span> <span>{r.key_points}</span></div>
                        {r.file_url && (
                          <a href={r.file_url} target="_blank" rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-primary hover:underline font-medium">
                            ↓ Download {r.file_name ?? "attachment"}
                          </a>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <Button variant="outline" size="sm" className="h-7 text-xs"
                      onClick={() => setExpandedReq(expandedReq === r.id ? null : r.id)}>
                      {expandedReq === r.id ? "Hide" : "View Details"}
                    </Button>
                    <Button size="sm" className="h-7 text-xs bg-green-500/15 text-green-400 border border-green-500/30 hover:bg-green-500/25"
                      variant="outline" onClick={() => handleReview(r.id)}>
                      <CheckCircle className="h-3 w-3" /> Mark Done
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showCreate && (
        <CreateUserDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); load(); }}
        />
      )}
    </div>
  );
}

// ── Create User Dialog ────────────────────────────────────────────────────────

function CreateUserDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState({ full_name: "", email: "", password: "", role: "member" });
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (!form.full_name.trim() || !form.email.trim() || !form.password.trim()) {
      toast.error("Fill all fields"); return;
    }
    if (form.password.length < 6) {
      toast.error("Password must be at least 6 characters"); return;
    }
    setSaving(true);
    try {
      await adminApi.createUser(form);
      toast.success(`${form.full_name} added to your team`);
      onCreated();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to create user");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Plus className="h-4 w-4" /> Add Team Member
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-1">
          <div className="space-y-1.5">
            <Label>Full Name</Label>
            <Input value={form.full_name} onChange={(e) => setForm(f => ({ ...f, full_name: e.target.value }))} placeholder="Priya Sharma" />
          </div>
          <div className="space-y-1.5">
            <Label>Email</Label>
            <Input type="email" value={form.email} onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))} placeholder="priya@yourcompany.com" />
          </div>
          <div className="space-y-1.5">
            <Label>Temporary Password</Label>
            <Input type="password" value={form.password} onChange={(e) => setForm(f => ({ ...f, password: e.target.value }))} placeholder="Min 6 characters" />
            <p className="text-xs text-muted-foreground">Share this with them — they can change it from their profile.</p>
          </div>
          <div className="space-y-1.5">
            <Label>Role</Label>
            <Select value={form.role} onValueChange={(v) => setForm(f => ({ ...f, role: v }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="member">Member — can manage campaigns</SelectItem>
                <SelectItem value="admin">Admin — full access</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button className="bg-gradient-primary text-white" onClick={handleSave} disabled={saving}>
            {saving ? <><Loader2 className="h-4 w-4 animate-spin" /> Adding…</> : "Add Member"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
