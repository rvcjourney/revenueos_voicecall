import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { CampaignBadge } from "@/components/layout/StatusBadge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Plus, Search, Calendar, Users, CheckCircle2, Heart, Megaphone,
  MoreVertical, Pause, Play, Loader2, Folder, FolderOpen,
  ChevronRight, Pencil, Trash2, X, Check,
} from "lucide-react";
import { useCampaigns, useFolders, useCreateFolder, useUpdateFolder, useDeleteFolder } from "@/lib/hooks";
import { campaignsApi, type FolderOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";

export const Route = createFileRoute("/_authed/campaigns/")({
  head: () => ({ meta: [{ title: "Campaigns — MOTMVoice" }] }),
  component: CampaignsList,
});

const FOLDER_COLORS = [
  "#3b82f6", "#22c55e", "#a855f7", "#f97316",
  "#ef4444", "#14b8a6", "#ec4899", "#f59e0b",
];

const FILTER_TABS = [
  { v: "all", l: "All" },
  { v: "running", l: "Active" },
  { v: "paused", l: "Paused" },
  { v: "completed", l: "Completed" },
  { v: "draft", l: "Draft" },
];

// ── New Folder Dialog ─────────────────────────────────────────────────────────
function FolderDialog({
  initial,
  onClose,
  onSave,
}: {
  initial?: { name: string; color: string | null };
  onClose: () => void;
  onSave: (name: string, color: string) => Promise<unknown>;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [color, setColor] = useState(initial?.color ?? FOLDER_COLORS[0]);
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (!name.trim()) { toast.error("Company name is required"); return; }
    setSaving(true);
    try { await onSave(name.trim(), color); onClose(); }
    catch { toast.error("Failed to save folder"); }
    finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-card border border-border rounded-xl shadow-xl w-full max-w-sm p-6 space-y-5">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-lg">{initial ? "Rename Folder" : "New Company Folder"}</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-1.5">
          <Label>Company Name</Label>
          <Input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSave()}
            placeholder="e.g. Acme Corp"
          />
        </div>
        <div className="space-y-1.5">
          <Label>Folder Color</Label>
          <div className="flex gap-2 flex-wrap">
            {FOLDER_COLORS.map((c) => (
              <button
                key={c}
                onClick={() => setColor(c)}
                className="h-7 w-7 rounded-full border-2 transition-transform hover:scale-110"
                style={{
                  backgroundColor: c,
                  borderColor: color === c ? "white" : "transparent",
                  boxShadow: color === c ? `0 0 0 2px ${c}` : "none",
                }}
              />
            ))}
          </div>
        </div>
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving} className="bg-gradient-primary text-white shadow-glow">
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            {initial ? "Save" : "Create Folder"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Campaign Card ─────────────────────────────────────────────────────────────
function CampaignCard({ c, onPause, onLaunch }: {
  c: any;
  onPause: (id: string) => void;
  onLaunch: (id: string) => void;
}) {
  const { isAdmin } = useAuth();
  const pct = c.total_contacts > 0 ? Math.round((c.completed_calls / c.total_contacts) * 100) : 0;
  return (
    <div className="rounded-xl bg-card border border-border p-5 hover:border-primary/40 transition-colors group">
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
          {c.created_by_name && (
            <p className="text-[11px] text-muted-foreground mt-1">
              by {c.created_by_name}
            </p>
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

      {/* Outcome breakdown mini bar */}
      {c.total_contacts > 0 && (
        <div className="mt-3">
          <div className="flex gap-px h-1.5 rounded-full overflow-hidden bg-surface-2">
            <div
              style={{ width: `${(c.interested_count / c.total_contacts) * 100}%`, background: "oklch(0.70 0.16 160)" }}
              title={`${c.interested_count} interested`}
            />
            <div
              style={{ width: `${(Math.max(0, c.completed_calls - c.interested_count) / c.total_contacts) * 100}%`, background: "oklch(0.565 0.240 284 / 0.45)" }}
              title="Other completed calls"
            />
          </div>
          <div className="flex items-center gap-3 mt-1 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: "oklch(0.70 0.16 160)" }} />
              {c.interested_count} interested
            </span>
            <span className="ml-auto font-mono">{c.completed_calls}/{c.total_contacts} called</span>
          </div>
        </div>
      )}

      <div className="mt-3 flex gap-2">
        <Link to="/campaigns/$id" params={{ id: c.id }} className="flex-1">
          <Button variant="outline" size="sm" className="w-full">View Details</Button>
        </Link>
        {c.status === "running" && (
          <>
            <Button variant="ghost" size="sm" title="Pause" onClick={() => onPause(c.id)}>
              <Pause className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="sm" title="Restart" onClick={() => onLaunch(c.id)}>
              <Play className="h-3.5 w-3.5 text-primary" />
            </Button>
          </>
        )}
        {(c.status === "paused" || c.status === "draft") && (
          <Button variant="ghost" size="sm" onClick={() => onLaunch(c.id)}>
            <Play className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    </div>
  );
}

// ── Folder Detail View (inside a folder) ─────────────────────────────────────
function FolderDetailView({ folder, onBack }: { folder: FolderOut; onBack: () => void }) {
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const qc = useQueryClient();
  const { isAdmin } = useAuth();

  const { data, isLoading } = useCampaigns(
    filter === "all" ? undefined : filter,
    folder.id,
  );
  const campaigns = (data?.items ?? []).filter((c) =>
    c.name.toLowerCase().includes(q.toLowerCase())
  );

  async function handlePause(id: string) {
    try { await campaignsApi.pause(id); qc.invalidateQueries({ queryKey: ["campaigns"] }); toast.success("Campaign paused"); }
    catch { toast.error("Failed to pause campaign"); }
  }
  async function handleLaunch(id: string) {
    try { await campaignsApi.launch(id); qc.invalidateQueries({ queryKey: ["campaigns"] }); toast.success("Campaign launched"); }
    catch (e: any) { toast.error(e?.response?.data?.detail ?? "Failed to launch campaign"); }
  }

  return (
    <div className="space-y-6 max-w-[1600px]">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ChevronRight className="h-4 w-4 rotate-180" />
            Campaigns
          </button>
          <span className="text-muted-foreground">/</span>
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded-md grid place-items-center" style={{ backgroundColor: folder.color ?? "#3b82f6" }}>
              <FolderOpen className="h-3.5 w-3.5 text-white" />
            </div>
            <h1 className="text-2xl font-bold">{folder.name}</h1>
          </div>
        </div>
        {!isAdmin && (
          <Link to="/campaigns/new" search={{ folderId: folder.id, folderName: folder.name }}>
            <Button className="bg-gradient-primary text-white shadow-glow">
              <Plus className="h-4 w-4" /> New Campaign
            </Button>
          </Link>
        )}
      </div>

      {/* Filters */}
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

      {/* Campaign grid */}
      {isLoading ? (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-xl bg-card border border-border p-5 animate-pulse space-y-3">
              <div className="h-5 w-28 rounded bg-surface-2" />
              <div className="h-3 w-40 rounded bg-surface-2" />
              <div className="grid grid-cols-4 gap-2">
                {[0, 1, 2, 3].map((j) => <div key={j} className="h-12 rounded-md bg-surface-2" />)}
              </div>
              <div className="h-1.5 rounded-full bg-surface-2" />
            </div>
          ))}
        </div>
      ) : campaigns.length === 0 ? (
        <div className="text-center py-20 rounded-xl bg-card border border-border">
          <div className="h-12 w-12 rounded-xl grid place-items-center mx-auto mb-4"
            style={{ backgroundColor: folder.color ?? "#3b82f6" }}>
            <Folder className="h-6 w-6 text-white" />
          </div>
          <h3 className="font-semibold text-lg">No campaigns in {folder.name}</h3>
          <p className="text-sm text-muted-foreground mt-1 mb-6">
            {isAdmin ? "Members can create campaigns in this folder." : "Create the first campaign for this company"}
          </p>
          {!isAdmin && (
            <Link to="/campaigns/new" search={{ folderId: folder.id, folderName: folder.name }}>
              <Button className="bg-gradient-primary text-white shadow-glow">
                <Plus className="h-4 w-4" /> Create Campaign
              </Button>
            </Link>
          )}
        </div>
      ) : (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
          {campaigns.map((c) => (
            <CampaignCard key={c.id} c={c} onPause={handlePause} onLaunch={handleLaunch} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Campaigns List (folder grid + uncategorized) ─────────────────────────
function CampaignsList() {
  const [selectedFolder, setSelectedFolder] = useState<FolderOut | null>(null);
  const [showNewFolder, setShowNewFolder] = useState(false);
  const [renamingFolder, setRenamingFolder] = useState<FolderOut | null>(null);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const qc = useQueryClient();
  const { isAdmin } = useAuth();

  const { data: folders, isLoading: foldersLoading } = useFolders();
  const createFolder = useCreateFolder();
  const updateFolder = useUpdateFolder();
  const deleteFolder = useDeleteFolder();

  const { data: uncatData, isLoading: uncatLoading } = useCampaigns(
    filter === "all" ? undefined : filter,
    "none",
  );
  const uncategorized = (uncatData?.items ?? []).filter((c) =>
    c.name.toLowerCase().includes(q.toLowerCase())
  );

  if (selectedFolder) {
    return <FolderDetailView folder={selectedFolder} onBack={() => setSelectedFolder(null)} />;
  }

  async function handlePause(id: string) {
    try { await campaignsApi.pause(id); qc.invalidateQueries({ queryKey: ["campaigns"] }); toast.success("Campaign paused"); }
    catch { toast.error("Failed to pause campaign"); }
  }
  async function handleLaunch(id: string) {
    try { await campaignsApi.launch(id); qc.invalidateQueries({ queryKey: ["campaigns"] }); toast.success("Campaign launched"); }
    catch (e: any) { toast.error(e?.response?.data?.detail ?? "Failed to launch campaign"); }
  }

  function handleDeleteFolder(id: string) {
    setDeleteConfirmId(id);
    setMenuOpenId(null);
  }

  return (
    <div className="space-y-8 max-w-[1600px]">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Campaigns</h1>
          <p className="text-sm text-muted-foreground mt-1">Organise campaigns by company folder</p>
        </div>
        <div className="flex gap-2">
          {!isAdmin && (
            <Button variant="outline" onClick={() => setShowNewFolder(true)}>
              <Folder className="h-4 w-4" /> New Folder
            </Button>
          )}
          {!isAdmin && (
            <Link to="/campaigns/new" search={{ folderId: undefined, folderName: undefined }}>
              <Button className="bg-gradient-primary text-white shadow-glow">
                <Plus className="h-4 w-4" /> Create Campaign
              </Button>
            </Link>
          )}
        </div>
      </div>

      {/* ── Company Folders ──────────────────────────────────────────────────── */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">Company Folders</h2>
        {foldersLoading ? (
          <div className="grid sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
            {[0, 1, 2].map((i) => (
              <div key={i} className="rounded-xl bg-card border border-border p-5 animate-pulse">
                <div className="flex items-start gap-3">
                  <div className="h-10 w-10 rounded-lg bg-surface-2 shrink-0" />
                  <div className="flex-1 space-y-2 pt-1">
                    <div className="h-3.5 w-24 rounded bg-surface-2" />
                    <div className="h-3 w-16 rounded bg-surface-2" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
            {(folders ?? []).map((folder) => (
              <div
                key={folder.id}
                className="relative rounded-xl bg-card border border-border p-5 hover:border-primary/40 transition-colors cursor-pointer group"
                onClick={() => setSelectedFolder(folder)}
              >
                {/* Folder icon + name */}
                <div className="flex items-start gap-3">
                  <div
                    className="h-10 w-10 rounded-lg grid place-items-center shrink-0"
                    style={{ backgroundColor: folder.color ?? "#3b82f6" }}
                  >
                    <Folder className="h-5 w-5 text-white" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold truncate">{folder.name}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {folder.campaign_count} campaign{folder.campaign_count !== 1 ? "s" : ""}
                    </p>
                  </div>
                </div>

                {/* "..." menu */}
                <button
                  className="absolute top-3 right-3 text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={(e) => { e.stopPropagation(); setMenuOpenId(menuOpenId === folder.id ? null : folder.id); }}
                >
                  <MoreVertical className="h-4 w-4" />
                </button>
                {menuOpenId === folder.id && (
                  <div
                    className="absolute top-8 right-3 z-10 bg-card border border-border rounded-lg shadow-lg py-1 min-w-[130px]"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      className="flex items-center gap-2 px-3 py-2 text-sm w-full hover:bg-surface-2 transition-colors"
                      onClick={() => { setRenamingFolder(folder); setMenuOpenId(null); }}
                    >
                      <Pencil className="h-3.5 w-3.5" /> Rename
                    </button>
                    <button
                      className="flex items-center gap-2 px-3 py-2 text-sm w-full hover:bg-surface-2 text-destructive transition-colors"
                      onClick={() => handleDeleteFolder(folder.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" /> Delete
                    </button>
                  </div>
                )}
              </div>
            ))}

            {/* New folder card — members only */}
            {!isAdmin && (
              <button
                onClick={() => setShowNewFolder(true)}
                className="rounded-xl border border-dashed border-border p-5 flex items-center gap-3 text-muted-foreground hover:text-foreground hover:border-primary/40 transition-colors"
              >
                <div className="h-10 w-10 rounded-lg border-2 border-dashed border-current grid place-items-center shrink-0">
                  <Plus className="h-5 w-5" />
                </div>
                <span className="text-sm font-medium">New Folder</span>
              </button>
            )}
          </div>
        )}
      </section>

      {/* ── Uncategorized Campaigns ───────────────────────────────────────────── */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
          Uncategorized Campaigns
        </h2>

        {/* Filters */}
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

        {uncatLoading ? (
          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
            {[0, 1, 2].map((i) => (
              <div key={i} className="rounded-xl bg-card border border-border p-5 animate-pulse space-y-3">
                <div className="h-5 w-28 rounded bg-surface-2" />
                <div className="h-3 w-40 rounded bg-surface-2" />
                <div className="grid grid-cols-4 gap-2">
                  {[0, 1, 2, 3].map((j) => <div key={j} className="h-12 rounded-md bg-surface-2" />)}
                </div>
                <div className="h-1.5 rounded-full bg-surface-2" />
              </div>
            ))}
          </div>
        ) : uncategorized.length === 0 ? (
          <div className="text-center py-14 rounded-xl bg-card border border-border">
            <div className="h-14 w-14 rounded-2xl bg-surface-2 grid place-items-center mx-auto mb-4">
              <Megaphone className="h-7 w-7 text-muted-foreground/30" />
            </div>
            <p className="text-base font-semibold text-foreground/70">No uncategorized campaigns</p>
            <p className="text-sm text-muted-foreground mt-1">All campaigns are organized in folders.</p>
          </div>
        ) : (
          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
            {uncategorized.map((c) => (
              <CampaignCard key={c.id} c={c} onPause={handlePause} onLaunch={handleLaunch} />
            ))}
          </div>
        )}
      </section>

      {/* New folder dialog */}
      {showNewFolder && (
        <FolderDialog
          onClose={() => setShowNewFolder(false)}
          onSave={(name, color) => createFolder.mutateAsync({ name, color })}
        />
      )}

      {/* Rename folder dialog */}
      {renamingFolder && (
        <FolderDialog
          initial={{ name: renamingFolder.name, color: renamingFolder.color }}
          onClose={() => setRenamingFolder(null)}
          onSave={(name, color) => updateFolder.mutateAsync({ id: renamingFolder.id, name, color })}
        />
      )}

      {/* Close dropdown on outside click */}
      {menuOpenId && (
        <div className="fixed inset-0 z-0" onClick={() => setMenuOpenId(null)} />
      )}

      {/* Delete folder confirmation */}
      {deleteConfirmId && (
        <AlertDialog open onOpenChange={(o) => !o && setDeleteConfirmId(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete this folder?</AlertDialogTitle>
              <AlertDialogDescription>
                Campaigns inside will become uncategorized. This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                className="bg-destructive text-white hover:bg-destructive/90"
                onClick={async () => {
                  try {
                    await deleteFolder.mutateAsync(deleteConfirmId);
                    toast.success("Folder deleted");
                  } catch {
                    toast.error("Failed to delete folder");
                  } finally {
                    setDeleteConfirmId(null);
                  }
                }}
              >
                Delete Folder
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
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
