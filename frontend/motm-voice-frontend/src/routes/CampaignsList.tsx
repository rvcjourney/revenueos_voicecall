import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Calendar, Folder, FolderOpen, Megaphone, Phone, Plus, Search, X } from "lucide-react";
import { useCampaigns, useCreateFolder, useFolders } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { CampaignStatusBadge } from "@/components/shared/StatusBadge";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { apiErrorMessage } from "@/lib/api";
import { cn, formatDate, initials } from "@/lib/utils";

const FOLDER_COLORS = ["#8FAE8B", "#C9A45C", "#7C98B3", "#C97B5C", "#A97CA5", "#9CA86B"];

const statusTabs = [
  { value: "all", label: "All" },
  { value: "running", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "completed", label: "Completed" },
  { value: "draft", label: "Draft" },
];

const STATUS_ACCENT: Record<string, string> = {
  draft: "var(--muted-foreground)",
  scheduled: "var(--info)",
  running: "var(--success)",
  paused: "var(--warning)",
  completed: "var(--primary)",
  failed: "var(--destructive)",
};

export default function CampaignsList() {
  const [status, setStatus] = useState("all");
  const [folderId, setFolderId] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const folders = useFolders();
  const campaigns = useCampaigns(status === "all" ? undefined : { status });

  const filtered = useMemo(() => {
    let list = campaigns.data ?? [];
    if (folderId) list = list.filter((c) => c.folder_id === folderId);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((c) => c.name.toLowerCase().includes(q));
    }
    return list;
  }, [campaigns.data, folderId, search]);

  const activeFolder = folders.data?.find((f) => f.id === folderId);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Campaigns"
        description="Organise campaigns by company folder"
        actions={
          <Button variant="gradient" asChild>
            <Link to="/campaigns/new">
              <Plus className="h-4 w-4" /> New Campaign
            </Link>
          </Button>
        }
      />

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Company Folders</p>
          <NewFolderDialog />
        </div>
        {folders.isError ? (
          <ErrorBanner error={folders.error} onRetry={() => folders.refetch()} />
        ) : folders.isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        ) : folders.data && folders.data.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {folders.data.map((f) => {
              const color = f.color ?? "#8FAE8B";
              const active = folderId === f.id;
              return (
                <button
                  key={f.id}
                  onClick={() => setFolderId(active ? null : f.id)}
                  className={cn(
                    "group relative flex flex-col overflow-hidden rounded-2xl border bg-card p-4 pt-5 text-left transition-all duration-200",
                    active
                      ? "border-transparent shadow-[var(--shadow-elevated)] -translate-y-0.5"
                      : "border-border hover:-translate-y-0.5 hover:shadow-[var(--shadow-elevated)]"
                  )}
                  style={active ? { boxShadow: `0 0 0 1.5px ${color}, var(--shadow-elevated)` } : undefined}
                >
                  <span className="absolute inset-x-0 top-0 h-1.5" style={{ backgroundColor: color }} />
                  <span
                    className="absolute -right-6 -top-6 h-20 w-20 rounded-full opacity-[0.12] transition-transform duration-300 group-hover:scale-125"
                    style={{ backgroundColor: color }}
                  />
                  <div className="relative flex items-start gap-3">
                    <span
                      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
                      style={{ backgroundColor: `${color}22`, color }}
                    >
                      {active ? <FolderOpen className="h-5 w-5" /> : <Folder className="h-5 w-5" />}
                    </span>
                    <div className="min-w-0 flex-1 pt-0.5">
                      <p className="truncate text-sm font-semibold">{f.name}</p>
                    </div>
                  </div>
                  <div className="relative mt-4 flex items-center justify-between">
                    <span
                      className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium"
                      style={{ backgroundColor: `${color}18`, color }}
                    >
                      {f.campaign_count} campaign{f.campaign_count === 1 ? "" : "s"}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No folders yet — create one to organise campaigns by company.</p>
        )}
      </section>

      <section className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {activeFolder ? activeFolder.name : "All Campaigns"}
            </p>
            {activeFolder && (
              <button onClick={() => setFolderId(null)} className="flex items-center gap-1 text-xs text-primary hover:underline">
                <X className="h-3 w-3" /> Clear
              </button>
            )}
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Tabs value={status} onValueChange={setStatus}>
              <TabsList>
                {statusTabs.map((t) => (
                  <TabsTrigger key={t.value} value={t.value}>
                    {t.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search campaigns..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-8 sm:w-56"
              />
            </div>
          </div>
        </div>

        {campaigns.isError ? (
          <ErrorBanner error={campaigns.error} onRetry={() => campaigns.refetch()} />
        ) : campaigns.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <Skeleton key={i} className="h-44 w-full" />
            ))}
          </div>
        ) : filtered.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((c) => {
              const pct = c.total_contacts ? Math.round((c.completed_calls / c.total_contacts) * 100) : 0;
              const accent = STATUS_ACCENT[c.status] ?? STATUS_ACCENT.draft;
              return (
                <Link key={c.id} to={`/campaigns/${c.id}`} className="group block h-full">
                  <div className="relative flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-[var(--shadow-card)] transition-all duration-200 group-hover:-translate-y-1 group-hover:shadow-[var(--shadow-elevated)]">
                    <span className="absolute inset-x-0 top-0 h-1.5" style={{ backgroundColor: accent }} />
                    <div className="flex flex-1 flex-col gap-4 p-5 pt-6">
                      <div className="flex items-start justify-between gap-3">
                        <p className="font-heading text-base font-semibold leading-snug">{c.name}</p>
                        <CampaignStatusBadge status={c.status} className="shrink-0" />
                      </div>

                      <div className="flex items-center gap-4 rounded-xl bg-muted/50 p-3">
                        <div
                          className="relative flex h-14 w-14 shrink-0 items-center justify-center rounded-full"
                          style={{ background: `conic-gradient(${accent} ${pct * 3.6}deg, var(--border) 0deg)` }}
                        >
                          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-card">
                            <span className="text-xs font-bold">{pct}%</span>
                          </div>
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5 text-sm font-medium">
                            <Phone className="h-3.5 w-3.5 text-muted-foreground" />
                            <span>
                              {c.completed_calls} / {c.total_contacts}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground">calls completed</p>
                        </div>
                      </div>

                      <div className="mt-auto flex items-center justify-between border-t border-border pt-3 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1.5">
                          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[image:var(--gradient-primary)] text-[9px] font-semibold text-primary-foreground">
                            {c.created_by_name ? initials(c.created_by_name) : "—"}
                          </span>
                          {c.created_by_name ?? "—"}
                        </span>
                        <span className="flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          {formatDate(c.created_at)}
                        </span>
                      </div>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        ) : (
          <EmptyState
            icon={Megaphone}
            title="No campaigns yet"
            description="Create your first campaign to start calling leads with an AI voice agent."
            action={
              <Button variant="gradient" asChild>
                <Link to="/campaigns/new">New campaign</Link>
              </Button>
            }
          />
        )}
      </section>
    </div>
  );
}

function NewFolderDialog() {
  const [open, setOpen] = useState(false);
  const createFolder = useCreateFolder();
  const { register, handleSubmit, reset, watch, setValue } = useForm<{ name: string; color: string }>({
    defaultValues: { name: "", color: FOLDER_COLORS[0] },
  });
  const color = watch("color");

  async function onSubmit(values: { name: string; color: string }) {
    try {
      await createFolder.mutateAsync(values);
      toast.success("Folder created");
      reset();
      setOpen(false);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't create folder"));
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Plus className="h-3.5 w-3.5" /> New folder
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New company folder</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="folder-name">Folder name</Label>
            <Input id="folder-name" placeholder="Acme Corp" {...register("name", { required: true })} />
          </div>
          <div className="space-y-1.5">
            <Label>Color</Label>
            <div className="flex gap-2">
              {FOLDER_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setValue("color", c)}
                  className={`h-7 w-7 rounded-full ${color === c ? "ring-2 ring-offset-2 ring-offset-popover ring-primary" : ""}`}
                  style={{ backgroundColor: c }}
                />
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button type="submit" variant="gradient" disabled={createFolder.isPending}>
              Create folder
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
