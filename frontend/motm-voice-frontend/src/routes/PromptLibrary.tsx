import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  BookMarked,
  Copy,
  Eye,
  History,
  Loader2,
  MoreVertical,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Star,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import {
  useCreatePrompt,
  useDeletePrompt,
  useMarkPromptPerformance,
  usePromptHistory,
  usePromptLibrary,
  useRestorePromptVersion,
  useSyncPromptsFromAgents,
  useUpdatePrompt,
} from "@/lib/hooks";
import { agentsApi, apiErrorMessage } from "@/lib/api";
import { cn, formatRelativeTime } from "@/lib/utils";
import type { PromptLibraryEntry } from "@/lib/types";

export default function PromptLibrary() {
  const { isAdmin } = useAuth();
  const [search, setSearch] = useState("");
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [selectedPrompt, setSelectedPrompt] = useState<PromptLibraryEntry | null>(null);
  const [selectedTab, setSelectedTab] = useState("prompt");
  const [formOpen, setFormOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState<PromptLibraryEntry | null>(null);

  const prompts = usePromptLibrary();
  const markPerformance = useMarkPromptPerformance();
  const deletePrompt = useDeletePrompt();
  const syncFromAgents = useSyncPromptsFromAgents();

  const allTags = useMemo(() => {
    const set = new Set<string>();
    (prompts.data ?? []).forEach((p) => p.tags.forEach((t) => set.add(t)));
    return Array.from(set).sort();
  }, [prompts.data]);

  // Only surface tags relevant to what's typed, instead of dumping the full
  // tag vocabulary on screen. The active tag stays visible even if it no
  // longer matches the search box, so it can still be cleared.
  const visibleTags = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const matches = needle ? allTags.filter((t) => t.includes(needle)) : [];
    if (activeTag && !matches.includes(activeTag)) matches.push(activeTag);
    return matches;
  }, [allTags, search, activeTag]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (prompts.data ?? []).filter((p) => {
      const matchesSearch =
        !needle ||
        p.title.toLowerCase().includes(needle) ||
        p.tags.some((t) => t.toLowerCase().includes(needle)) ||
        p.structured_prompt.toLowerCase().includes(needle);
      const matchesTag = !activeTag || p.tags.includes(activeTag);
      return matchesSearch && matchesTag;
    });
  }, [prompts.data, search, activeTag]);

  // Keep the open sheet's data fresh after a mutation invalidates the list.
  useEffect(() => {
    if (!selectedPrompt) return;
    const fresh = prompts.data?.find((p) => p.id === selectedPrompt.id);
    if (fresh && fresh !== selectedPrompt) setSelectedPrompt(fresh);
  }, [prompts.data, selectedPrompt]);

  function openPreview(prompt: PromptLibraryEntry, tab: "prompt" | "history" = "prompt") {
    setSelectedPrompt(prompt);
    setSelectedTab(tab);
  }

  function openCreate() {
    setEditingEntry(null);
    setFormOpen(true);
  }

  function openEdit(prompt: PromptLibraryEntry) {
    setEditingEntry(prompt);
    setFormOpen(true);
  }

  async function toggleHighPerforming(prompt: PromptLibraryEntry) {
    try {
      await markPerformance.mutateAsync({ id: prompt.id, is_high_performing: !prompt.is_high_performing });
      toast.success(prompt.is_high_performing ? "Unmarked as high-performing" : "Marked as high-performing");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't update"));
    }
  }

  async function handleDelete(prompt: PromptLibraryEntry) {
    if (!confirm(`Delete "${prompt.title}"? This can't be undone.`)) return;
    try {
      await deletePrompt.mutateAsync(prompt.id);
      toast.success("Prompt deleted");
      if (selectedPrompt?.id === prompt.id) setSelectedPrompt(null);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't delete prompt"));
    }
  }

  async function handleSync() {
    try {
      const res = await syncFromAgents.mutateAsync();
      toast.success(res.data.message);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't sync from agents"));
    }
  }

  async function copyPrompt(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Copied to clipboard");
    } catch {
      toast.error("Couldn't copy — clipboard access denied");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Prompt Library"
        description="Admin-curated system prompts your team can reuse. Anyone can mark a prompt as high-performing once it proves itself with real leads."
        actions={
          isAdmin && (
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={handleSync} disabled={syncFromAgents.isPending}>
                {syncFromAgents.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                Sync from agents
              </Button>
              <Button variant="gradient" onClick={openCreate}>
                <Plus className="h-4 w-4" /> New Prompt
              </Button>
            </div>
          )
        }
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by use case, e.g. paint, laptop repair..."
            className="pl-9"
          />
        </div>
        {visibleTags.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              onClick={() => setActiveTag(null)}
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                !activeTag
                  ? "border-transparent bg-primary/15 text-primary"
                  : "border-border text-muted-foreground hover:text-foreground"
              )}
            >
              All
            </button>
            {visibleTags.map((tag) => (
              <button
                key={tag}
                onClick={() => setActiveTag(tag === activeTag ? null : tag)}
                className={cn(
                  "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                  activeTag === tag
                    ? "border-transparent bg-primary/15 text-primary"
                    : "border-border text-muted-foreground hover:text-foreground"
                )}
              >
                {tag}
              </button>
            ))}
          </div>
        )}
      </div>

      {prompts.isError ? (
        <ErrorBanner error={prompts.error} onRetry={() => prompts.refetch()} />
      ) : prompts.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-52 w-full" />)}
        </div>
      ) : filtered.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((prompt) => (
            <PromptCard
              key={prompt.id}
              prompt={prompt}
              isAdmin={isAdmin}
              onToggleHighPerforming={() => toggleHighPerforming(prompt)}
              onPreview={() => openPreview(prompt, "prompt")}
              onHistory={() => openPreview(prompt, "history")}
              onEdit={() => openEdit(prompt)}
              onDelete={() => handleDelete(prompt)}
              onCopy={() => copyPrompt(prompt.structured_prompt)}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={BookMarked}
          title={prompts.data && prompts.data.length > 0 ? "No prompts match your filters" : "No prompts yet"}
          description={
            prompts.data && prompts.data.length > 0
              ? "Try a different search term or clear the tag filter."
              : isAdmin
                ? "Create one, or sync your existing agents' prompts into the library."
                : "Ask an admin to add prompts to the library."
          }
          action={
            isAdmin && !(prompts.data && prompts.data.length > 0) ? (
              <Button variant="gradient" onClick={openCreate}>Create prompt</Button>
            ) : undefined
          }
        />
      )}

      <PromptDetailSheet
        prompt={selectedPrompt}
        isAdmin={isAdmin}
        tab={selectedTab}
        onTabChange={setSelectedTab}
        onOpenChange={(open) => !open && setSelectedPrompt(null)}
        onToggleHighPerforming={() => selectedPrompt && toggleHighPerforming(selectedPrompt)}
        onCopy={() => selectedPrompt && copyPrompt(selectedPrompt.structured_prompt)}
      />

      <PromptFormDialog open={formOpen} onOpenChange={setFormOpen} entry={editingEntry} />
    </div>
  );
}

function PromptCard({
  prompt,
  isAdmin,
  onToggleHighPerforming,
  onPreview,
  onHistory,
  onEdit,
  onDelete,
  onCopy,
}: {
  prompt: PromptLibraryEntry;
  isAdmin: boolean;
  onToggleHighPerforming: () => void;
  onPreview: () => void;
  onHistory: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onCopy: () => void;
}) {
  const accent = prompt.is_high_performing ? "var(--success)" : "var(--border)";

  return (
    <div className="relative flex h-full flex-col overflow-hidden rounded-xl border border-border bg-card shadow-[var(--shadow-card)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow-elevated)]">
      <span className="absolute inset-x-0 top-0 h-1" style={{ backgroundColor: accent }} />
      <div className="flex flex-1 flex-col gap-3 p-3.5 pt-4">
        <div className="flex items-start gap-2.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[image:var(--gradient-primary)]">
            <BookMarked className="h-4 w-4 text-primary-foreground" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold leading-tight">{prompt.title}</p>
            <p className="truncate text-[11px] text-muted-foreground">
              {prompt.source_agent_name ? `from ${prompt.source_agent_name}` : `by ${prompt.created_by_name}`}
            </p>
          </div>
          <button
            onClick={onToggleHighPerforming}
            title={prompt.is_high_performing ? "Unmark as high-performing" : "Mark as high-performing"}
            className={cn(
              "shrink-0 rounded-md p-1 transition-colors",
              prompt.is_high_performing ? "text-warning" : "text-muted-foreground/40 hover:text-warning"
            )}
          >
            <Star className={cn("h-4 w-4", prompt.is_high_performing && "fill-current")} />
          </button>
        </div>

        {prompt.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {prompt.tags.map((tag) => (
              <Badge key={tag} variant="muted" className="text-[10px]">{tag}</Badge>
            ))}
          </div>
        )}

        <p className="line-clamp-3 text-xs leading-relaxed text-muted-foreground">
          {prompt.structured_prompt}
        </p>

        <div className="mt-auto flex items-center justify-between border-t border-border pt-2.5 text-[11px] text-muted-foreground">
          <span>v{prompt.current_version} · {formatRelativeTime(prompt.updated_at)}</span>
        </div>

        <div className="flex gap-1.5">
          <Button variant="outline" size="sm" className="flex-1" onClick={onPreview}>
            <Eye className="h-3.5 w-3.5" /> Preview
          </Button>
          <Button variant="outline" size="icon" onClick={onCopy} title="Copy">
            <Copy className="h-3.5 w-3.5" />
          </Button>
          {isAdmin && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon" title="More">
                  <MoreVertical className="h-3.5 w-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={onEdit}>
                  <Pencil className="h-3.5 w-3.5" /> Edit
                </DropdownMenuItem>
                <DropdownMenuItem onClick={onHistory}>
                  <History className="h-3.5 w-3.5" /> Version history
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onDelete} className="text-destructive focus:text-destructive">
                  <Trash2 className="h-3.5 w-3.5" /> Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
    </div>
  );
}

function PromptDetailSheet({
  prompt,
  isAdmin,
  tab,
  onTabChange,
  onOpenChange,
  onToggleHighPerforming,
  onCopy,
}: {
  prompt: PromptLibraryEntry | null;
  isAdmin: boolean;
  tab: string;
  onTabChange: (t: string) => void;
  onOpenChange: (open: boolean) => void;
  onToggleHighPerforming: () => void;
  onCopy: () => void;
}) {
  const navigate = useNavigate();
  const history = usePromptHistory(prompt?.id);
  const restoreVersion = useRestorePromptVersion();

  function useInAgent() {
    if (!prompt) return;
    navigate("/agents", { state: { prefillSystemPrompt: prompt.structured_prompt } });
  }

  async function handleRestore(version: number) {
    if (!prompt) return;
    try {
      await restoreVersion.mutateAsync({ id: prompt.id, version });
      toast.success(`Restored v${version}`);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't restore version"));
    }
  }

  return (
    <Sheet open={!!prompt} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-xl">
        {prompt && (
          <>
            <SheetHeader>
              <div className="flex items-start justify-between gap-3 pr-6">
                <div>
                  <SheetTitle>{prompt.title}</SheetTitle>
                  <SheetDescription>
                    v{prompt.current_version} · by {prompt.created_by_name} · updated {formatRelativeTime(prompt.updated_at)}
                  </SheetDescription>
                </div>
                <button
                  onClick={onToggleHighPerforming}
                  title={prompt.is_high_performing ? "Unmark as high-performing" : "Mark as high-performing"}
                  className={cn(
                    "shrink-0 rounded-md p-1 transition-colors",
                    prompt.is_high_performing ? "text-warning" : "text-muted-foreground/40 hover:text-warning"
                  )}
                >
                  <Star className={cn("h-5 w-5", prompt.is_high_performing && "fill-current")} />
                </button>
              </div>
              <div className="flex flex-wrap gap-1 pt-1">
                {prompt.tags.map((t) => (
                  <Badge key={t} variant="muted" className="text-[10px]">{t}</Badge>
                ))}
                {prompt.is_high_performing && (
                  <Badge variant="warning" className="text-[10px]">
                    <Star className="h-2.5 w-2.5 fill-current" /> High-performing
                  </Badge>
                )}
              </div>
            </SheetHeader>

            <Tabs value={tab} onValueChange={onTabChange} className="mt-2">
              <TabsList>
                <TabsTrigger value="prompt">Prompt</TabsTrigger>
                <TabsTrigger value="history">History{history.data ? ` (${history.data.length})` : ""}</TabsTrigger>
              </TabsList>

              <TabsContent value="prompt" className="space-y-3">
                <div className="max-h-[55vh] overflow-y-auto rounded-lg border border-border bg-muted/40 p-4">
                  <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-foreground">
                    {prompt.structured_prompt}
                  </pre>
                </div>
                <div className="flex gap-2">
                  <Button variant="gradient" className="flex-1" onClick={useInAgent}>
                    <Sparkles className="h-4 w-4" /> Use in this agent
                  </Button>
                  <Button variant="outline" onClick={onCopy}>
                    <Copy className="h-4 w-4" /> Copy
                  </Button>
                </div>
              </TabsContent>

              <TabsContent value="history" className="space-y-2">
                {history.isLoading ? (
                  <div className="space-y-2">
                    <Skeleton className="h-16 w-full" />
                    <Skeleton className="h-16 w-full" />
                  </div>
                ) : (
                  (history.data ?? []).map((h) => (
                    <div
                      key={h.version}
                      className="flex items-start justify-between gap-3 rounded-lg border border-border p-3"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge variant="secondary" className="text-[10px]">v{h.version}</Badge>
                          <span className="text-xs font-medium">{h.editor_name}</span>
                          <span className="text-[11px] text-muted-foreground">{formatRelativeTime(h.created_at)}</span>
                        </div>
                        {h.note && <p className="mt-1 text-xs text-muted-foreground">{h.note}</p>}
                      </div>
                      {isAdmin && h.version !== prompt.current_version && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="shrink-0"
                          onClick={() => handleRestore(h.version)}
                          disabled={restoreVersion.isPending}
                        >
                          Restore
                        </Button>
                      )}
                    </div>
                  ))
                )}
              </TabsContent>
            </Tabs>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function PromptFormDialog({
  open,
  onOpenChange,
  entry,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  entry: PromptLibraryEntry | null;
}) {
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [rawInput, setRawInput] = useState("");
  const [structuredPrompt, setStructuredPrompt] = useState("");
  const [note, setNote] = useState("");
  const [optimizing, setOptimizing] = useState(false);
  const createPrompt = useCreatePrompt();
  const updatePrompt = useUpdatePrompt();

  useEffect(() => {
    if (!open) return;
    setTitle(entry?.title ?? "");
    setTags(entry?.tags.join(", ") ?? "");
    setRawInput(entry?.raw_input ?? "");
    setStructuredPrompt(entry?.structured_prompt ?? "");
    setNote("");
  }, [open, entry]);

  async function handleOptimize() {
    if (!rawInput.trim()) {
      toast.error("Write a rough prompt first, then optimize it");
      return;
    }
    setOptimizing(true);
    try {
      const res = await agentsApi.optimizePrompt(rawInput);
      setStructuredPrompt(res.data.optimized_prompt);
      toast.success("Prompt optimized");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't optimize prompt"));
    } finally {
      setOptimizing(false);
    }
  }

  async function handleSave() {
    if (!title.trim()) {
      toast.error("Title is required");
      return;
    }
    if (!structuredPrompt.trim()) {
      toast.error("Structured prompt is required");
      return;
    }
    const tagList = tags.split(",").map((t) => t.trim()).filter(Boolean);
    try {
      if (entry) {
        await updatePrompt.mutateAsync({
          id: entry.id,
          data: { title, tags: tagList, structured_prompt: structuredPrompt, note: note || undefined },
        });
        toast.success("Prompt updated");
      } else {
        await createPrompt.mutateAsync({
          title,
          tags: tagList,
          raw_input: rawInput || undefined,
          structured_prompt: structuredPrompt,
        });
        toast.success("Prompt added to library");
      }
      onOpenChange(false);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't save prompt"));
    }
  }

  const saving = createPrompt.isPending || updatePrompt.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{entry ? "Edit library prompt" : "New library prompt"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Title</Label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Real Estate — Warm Lead Qualifier" />
            </div>
            <div className="space-y-1.5">
              <Label>Tags</Label>
              <Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="real-estate, qualifying" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Raw input</Label>
            <Textarea
              value={rawInput}
              onChange={(e) => setRawInput(e.target.value)}
              rows={4}
              placeholder="Paste rough notes about the agent's persona, product, and how it should qualify leads..."
            />
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>Structured prompt</Label>
              <Button type="button" variant="ghost" size="sm" onClick={handleOptimize} disabled={optimizing}>
                {optimizing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                Structure with AI
              </Button>
            </div>
            <Textarea
              value={structuredPrompt}
              onChange={(e) => setStructuredPrompt(e.target.value)}
              rows={8}
              placeholder="The structured prompt goes here..."
            />
          </div>
          {entry && (
            <div className="space-y-1.5">
              <Label>Edit summary (optional)</Label>
              <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="What changed and why" />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="gradient" onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            {entry ? "Save changes" : "Save to library"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
