import { useState } from "react";
import { toast } from "sonner";
import {
  Check,
  Clock,
  Copy,
  FileText,
  KeyRound,
  Loader2,
  Megaphone,
  Phone,
  Plus,
  Shield,
  ShieldCheck,
  ShieldOff,
  ThumbsUp,
  UserCheck,
  UserPlus,
  Users,
  X,
  Zap,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { RoleBadge } from "@/components/shared/StatusBadge";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAdminOrg,
  useAdminStats,
  useAdminUsers,
  useAgentAccessList,
  useAgentCreationRequestsAdmin,
  useAgentRequests,
} from "@/lib/hooks";
import { adminApi, apiErrorMessage } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import { cn, formatDate, initials } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

export default function AdminTeam() {
  return (
    <div className="space-y-6">
      <PageHeader title="Team" description="Manage your sales team members and their access" />

      <Tabs defaultValue="members">
        <TabsList className="h-11 gap-1 rounded-xl p-1.5">
          <TabsTrigger value="members" className="gap-1.5 rounded-lg px-3.5 py-1.5">
            <Users className="h-3.5 w-3.5" /> Members
          </TabsTrigger>
          <TabsTrigger value="agent-access" className="gap-1.5 rounded-lg px-3.5 py-1.5">
            <ShieldCheck className="h-3.5 w-3.5" /> Agent Access
          </TabsTrigger>
          <TabsTrigger value="agent-requests" className="gap-1.5 rounded-lg px-3.5 py-1.5">
            <FileText className="h-3.5 w-3.5" /> Agent Requests
          </TabsTrigger>
        </TabsList>
        <TabsContent value="members"><MembersTab /></TabsContent>
        <TabsContent value="agent-access"><AgentAccessTab /></TabsContent>
        <TabsContent value="agent-requests"><AgentCreationRequestsTab /></TabsContent>
      </Tabs>
    </div>
  );
}

function MembersTab() {
  const org = useAdminOrg();
  const stats = useAdminStats();
  const users = useAdminUsers();
  const [copied, setCopied] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const qc = useQueryClient();

  function copyCode() {
    if (!org.data) return;
    navigator.clipboard.writeText(org.data.invite_code);
    setCopied(true);
    toast.success("Invite code copied");
    setTimeout(() => setCopied(false), 1500);
  }

  async function toggleActive(id: string, is_active: boolean) {
    try {
      await adminApi.updateUser(id, { is_active });
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      toast.success(is_active ? "User reactivated" : "User deactivated");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't update user"));
    }
  }

  return (
    <div className="space-y-6">
      <div className="relative overflow-hidden rounded-2xl border border-border bg-card shadow-[var(--shadow-card)]">
        <span className="absolute inset-x-0 top-0 h-1.5 bg-[image:var(--gradient-primary)]" />
        <div className="flex flex-col gap-4 p-5 pt-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[image:var(--gradient-primary)] text-primary-foreground">
              <KeyRound className="h-5 w-5" />
            </span>
            <div>
              <p className="text-sm font-semibold">Team Invite Code</p>
              <p className="text-xs text-muted-foreground">Share this with new members to join on the sign-up page.</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {org.isLoading ? (
              <Skeleton className="h-10 w-40" />
            ) : (
              <code className="rounded-lg border border-border bg-muted px-4 py-2.5 text-sm font-mono font-semibold tracking-widest">
                {org.data?.invite_code}
              </code>
            )}
            <Button variant="outline" size="icon" onClick={copyCode} disabled={!org.data}>
              {copied ? <Check className="h-4 w-4 text-success" /> : <Copy className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>

      {stats.data && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <StatCard icon={Users} label="Members" value={stats.data.totals.total_members} />
          <StatCard icon={Megaphone} label="Total Campaigns" value={stats.data.totals.total_campaigns} />
          <StatCard icon={Phone} label="Total Calls" value={stats.data.totals.total_calls} tone="info" />
          <StatCard icon={ThumbsUp} label="Interested" value={stats.data.totals.total_interested} tone="success" />
          <StatCard icon={Zap} label="Active Campaigns" value={stats.data.totals.active_campaigns} tone="warning" />
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold">User Performance</p>
          <p className="text-xs text-muted-foreground">Everyone with access to this workspace</p>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button variant="gradient" size="sm"><UserPlus className="h-3.5 w-3.5" /> Add member</Button>
          </DialogTrigger>
          <CreateUserDialogContent onDone={() => setCreateOpen(false)} />
        </Dialog>
      </div>

      {users.isError ? (
        <ErrorBanner error={users.error} onRetry={() => users.refetch()} />
      ) : users.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <Card className="overflow-hidden py-0">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="pl-5">Member</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last login</TableHead>
                <TableHead className="pr-5 text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.data?.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="pl-5">
                    <div className="flex items-center gap-2.5">
                      <Avatar className="h-8 w-8 ring-2 ring-border">
                        <AvatarFallback>{initials(u.full_name)}</AvatarFallback>
                      </Avatar>
                      <div>
                        <p className="text-sm font-medium">{u.full_name}</p>
                        <p className="text-xs text-muted-foreground">{u.email}</p>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell><RoleBadge role={u.role} /></TableCell>
                  <TableCell>
                    <span
                      className={cn(
                        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
                        u.is_active ? "bg-success/15 text-success" : "bg-muted text-muted-foreground"
                      )}
                    >
                      <span className={cn("h-1.5 w-1.5 rounded-full bg-current", u.is_active && "animate-pulse-glow")} />
                      {u.is_active ? "Active" : "Deactivated"}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{u.last_login_at ? formatDate(u.last_login_at) : "Never"}</TableCell>
                  <TableCell className="pr-5 text-right">
                    <Button variant="ghost" size="sm" onClick={() => toggleActive(u.id, !u.is_active)}>
                      {u.is_active ? <><ShieldOff className="h-3.5 w-3.5" /> Deactivate</> : <><Shield className="h-3.5 w-3.5" /> Reactivate</>}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}

function CreateUserDialogContent({ onDone }: { onDone: () => void }) {
  const [form, setForm] = useState({ full_name: "", email: "", password: "", role: "member" });
  const [submitting, setSubmitting] = useState(false);
  const qc = useQueryClient();

  async function handleSubmit() {
    if (!form.full_name.trim() || !form.email.trim() || form.password.length < 6) {
      toast.error("Fill all fields — password needs at least 6 characters");
      return;
    }
    setSubmitting(true);
    try {
      await adminApi.createUser(form);
      toast.success("Team member added");
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      onDone();
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't add team member"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <DialogContent>
      <DialogHeader><DialogTitle>Add team member</DialogTitle></DialogHeader>
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label>Full name</Label>
          <Input value={form.full_name} onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} />
        </div>
        <div className="space-y-1.5">
          <Label>Email</Label>
          <Input type="email" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
        </div>
        <div className="space-y-1.5">
          <Label>Password</Label>
          <Input type="password" placeholder="Min. 6 characters" value={form.password} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} />
        </div>
        <div className="space-y-1.5">
          <Label>Role</Label>
          <Select value={form.role} onValueChange={(v) => setForm((f) => ({ ...f, role: v }))}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="member">Member</SelectItem>
              <SelectItem value="admin">Admin</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <DialogFooter>
        <Button variant="gradient" onClick={handleSubmit} disabled={submitting}>
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          Add member
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}

function AgentAccessTab() {
  const pending = useAgentRequests("pending");
  const approved = useAgentAccessList();
  const qc = useQueryClient();

  async function approve(id: string) {
    try {
      await adminApi.approveAgentRequest(id);
      qc.invalidateQueries({ queryKey: ["agent-requests"] });
      qc.invalidateQueries({ queryKey: ["agent-access"] });
      qc.invalidateQueries({ queryKey: ["agents"] });
      toast.success("Access approved");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't approve request"));
    }
  }
  async function reject(id: string) {
    try {
      await adminApi.rejectAgentRequest(id);
      qc.invalidateQueries({ queryKey: ["agent-requests"] });
      qc.invalidateQueries({ queryKey: ["agents"] });
      toast.success("Request rejected");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't reject request"));
    }
  }
  async function revoke(id: string) {
    try {
      await adminApi.revokeAgentAccess(id);
      qc.invalidateQueries({ queryKey: ["agent-access"] });
      qc.invalidateQueries({ queryKey: ["agents"] });
      toast.success("Access revoked");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't revoke access"));
    }
  }
  async function toggleEdit(id: string, can_edit: boolean) {
    try {
      await adminApi.setEditPermission(id, can_edit);
      qc.invalidateQueries({ queryKey: ["agent-access"] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't update permission"));
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-3 flex items-center gap-2">
          <Clock className="h-4 w-4 text-warning" />
          <p className="text-sm font-semibold">Pending requests</p>
          {pending.data && pending.data.length > 0 && (
            <span className="rounded-full bg-warning/15 px-2 py-0.5 text-xs font-medium text-warning">{pending.data.length}</span>
          )}
        </div>
        {pending.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : pending.data && pending.data.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {pending.data.map((r) => (
              <div
                key={r.id}
                className="relative overflow-hidden rounded-2xl border border-border bg-card p-4 shadow-[var(--shadow-card)]"
              >
                <span className="absolute inset-x-0 top-0 h-1.5" style={{ backgroundColor: "var(--warning)" }} />
                <div className="flex items-start gap-3 pt-1">
                  <Avatar className="h-9 w-9 shrink-0"><AvatarFallback>{initials(r.user_name)}</AvatarFallback></Avatar>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium leading-snug">
                      {r.user_name} <span className="font-normal text-muted-foreground">wants access to</span> {r.agent_name}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">{r.user_email} · {formatDate(r.created_at)}</p>
                  </div>
                </div>
                <div className="mt-3 flex gap-2 border-t border-border pt-3">
                  <Button size="sm" variant="gradient" className="flex-1" onClick={() => approve(r.id)}>
                    <Check className="h-3.5 w-3.5" /> Approve
                  </Button>
                  <Button size="sm" variant="outline" className="flex-1" onClick={() => reject(r.id)}>
                    <X className="h-3.5 w-3.5" /> Reject
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No pending requests" description="Access requests from your team will show up here." />
        )}
      </div>

      <div>
        <div className="mb-3 flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-success" />
          <p className="text-sm font-semibold">Approved access</p>
        </div>
        {approved.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : approved.data && approved.data.length > 0 ? (
          <Card className="overflow-hidden py-0">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="pl-5">Member</TableHead>
                  <TableHead>Agent</TableHead>
                  <TableHead>Last used</TableHead>
                  <TableHead>Can edit</TableHead>
                  <TableHead className="pr-5 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {approved.data.map((a) => (
                  <TableRow key={a.request_id}>
                    <TableCell className="pl-5">
                      <div className="flex items-center gap-2.5">
                        <Avatar className="h-8 w-8 ring-2 ring-border"><AvatarFallback>{initials(a.user_name)}</AvatarFallback></Avatar>
                        <div>
                          <p className="text-sm font-medium">{a.user_name}</p>
                          <p className="text-xs text-muted-foreground">{a.user_email}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
                        {a.agent_name}
                      </span>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {a.last_used_at ? formatDate(a.last_used_at) : "Never"}
                      {a.last_campaign_name && ` · ${a.last_campaign_name}`}
                    </TableCell>
                    <TableCell>
                      <Switch checked={a.can_edit} onCheckedChange={(v) => toggleEdit(a.request_id, v)} />
                    </TableCell>
                    <TableCell className="pr-5 text-right">
                      <Button variant="ghost" size="sm" onClick={() => revoke(a.request_id)}>Revoke</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        ) : (
          <EmptyState title="No approved access yet" description="Approved agent access grants will appear here." />
        )}
      </div>
    </div>
  );
}

function AgentCreationRequestsTab() {
  const requests = useAgentCreationRequestsAdmin();
  const qc = useQueryClient();

  async function markReviewed(id: string) {
    try {
      await adminApi.reviewAgentCreationRequest(id, "Reviewed");
      qc.invalidateQueries({ queryKey: ["agent-creation-requests-admin"] });
      toast.success("Marked as reviewed");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't update request"));
    }
  }

  if (requests.isLoading) return <Skeleton className="h-40 w-full" />;
  if (!requests.data || requests.data.length === 0) {
    return <EmptyState icon={Plus} title="No agent creation requests" description="Requests submitted by your team for new agents will appear here." />;
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {requests.data.map((r) => {
        const isPending = r.status === "pending";
        return (
          <div
            key={r.id}
            className="relative flex flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-[var(--shadow-card)]"
          >
            <span
              className="absolute inset-x-0 top-0 h-1.5"
              style={{ backgroundColor: isPending ? "var(--warning)" : "var(--success)" }}
            />
            <div className="flex flex-1 flex-col gap-3 p-5 pt-6">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-start gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <FileText className="h-4 w-4" />
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold leading-snug">
                      {r.agent_name} <span className="font-normal text-muted-foreground">for</span> {r.company_name}
                    </p>
                    <p className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
                      <UserCheck className="h-3 w-3" /> {r.user_name} · {formatDate(r.created_at)}
                    </p>
                  </div>
                </div>
                <span
                  className={cn(
                    "shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
                    isPending ? "bg-warning/15 text-warning" : "bg-success/15 text-success"
                  )}
                >
                  {r.status}
                </span>
              </div>

              <div className="grid gap-2.5 rounded-xl bg-muted/50 p-3 text-sm sm:grid-cols-2">
                <p><span className="text-xs text-muted-foreground">Product/service</span><br />{r.product_service}</p>
                <p><span className="text-xs text-muted-foreground">Target customers</span><br />{r.target_customers}</p>
              </div>
              <p className="text-sm"><span className="text-xs text-muted-foreground">Key points</span><br />{r.key_points}</p>

              <div className="mt-auto flex items-center justify-between border-t border-border pt-3">
                {r.file_url ? (
                  <a href={r.file_url} target="_blank" rel="noreferrer" className="text-xs font-medium text-primary hover:underline">
                    View attached file
                  </a>
                ) : <span />}
                {isPending && (
                  <Button size="sm" variant="outline" onClick={() => markReviewed(r.id)}>Mark reviewed</Button>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
