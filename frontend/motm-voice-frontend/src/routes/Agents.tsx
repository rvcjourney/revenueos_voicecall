import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Bot,
  Headset,
  Loader2,
  Lock,
  Pencil,
  Phone,
  Plus,
  Sparkles,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AgentAccessBadge } from "@/components/shared/StatusBadge";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import {
  useAgents,
  useClonedVoices,
  useCreateAgent,
  useDeleteAgent,
  useRequestAgentAccess,
  useUpdateAgent,
  useMyTrunks,
} from "@/lib/hooks";
import { agentsApi, apiErrorMessage } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { AgentCreate, AgentTemplate } from "@/lib/types";

const VOICE_PROVIDERS = ["elevenlabs", "sarvam"];
const LLM_MODELS = ["llama-3.3-70b-versatile", "qwen/qwen3.6-27b", "openai/gpt-oss-20b", "llama-3.1-8b-instant"];

// Sarvam's Bulbul v3 speaker catalog is a fixed, documented set (not a live
// per-account list the way ElevenLabs' is) — sourced directly from the
// installed livekit-plugins-sarvam SDK's MODEL_SPEAKER_COMPATIBILITY table
// for the "bulbul:v3" model (see agent/config.py's SARVAM_MODEL), not
// guessed. Kept here rather than round-tripping to the backend since it
// never changes without a plugin upgrade.
//
// `focus` mirrors that same SDK table's own grouping: everything under its
// "Customer Care" and "Content Creation" headings is a native Hindi/Hinglish
// voice (this platform's primary use case); only "International" (Amelia,
// Sophia) is an English-accented voice not tuned for Hindi.
const SARVAM_VOICES: { id: string; name: string; gender: "male" | "female"; focus: "hindi" | "international" }[] = [
  { id: "shubh", name: "Shubh", gender: "male", focus: "hindi" },
  { id: "ritu", name: "Ritu", gender: "female", focus: "hindi" },
  { id: "rahul", name: "Rahul", gender: "male", focus: "hindi" },
  { id: "pooja", name: "Pooja", gender: "female", focus: "hindi" },
  { id: "simran", name: "Simran", gender: "female", focus: "hindi" },
  { id: "kavya", name: "Kavya", gender: "female", focus: "hindi" },
  { id: "amit", name: "Amit", gender: "male", focus: "hindi" },
  { id: "ratan", name: "Ratan", gender: "male", focus: "hindi" },
  { id: "rohan", name: "Rohan", gender: "male", focus: "hindi" },
  { id: "dev", name: "Dev", gender: "male", focus: "hindi" },
  { id: "ishita", name: "Ishita", gender: "female", focus: "hindi" },
  { id: "shreya", name: "Shreya", gender: "female", focus: "hindi" },
  { id: "manan", name: "Manan", gender: "male", focus: "hindi" },
  { id: "sumit", name: "Sumit", gender: "male", focus: "hindi" },
  { id: "priya", name: "Priya", gender: "female", focus: "hindi" },
  { id: "aditya", name: "Aditya", gender: "male", focus: "hindi" },
  { id: "kabir", name: "Kabir", gender: "male", focus: "hindi" },
  { id: "neha", name: "Neha", gender: "female", focus: "hindi" },
  { id: "varun", name: "Varun", gender: "male", focus: "hindi" },
  { id: "roopa", name: "Roopa", gender: "female", focus: "hindi" },
  { id: "aayan", name: "Aayan", gender: "male", focus: "hindi" },
  { id: "ashutosh", name: "Ashutosh", gender: "male", focus: "hindi" },
  { id: "advait", name: "Advait", gender: "male", focus: "hindi" },
  { id: "amelia", name: "Amelia", gender: "female", focus: "international" },
  { id: "sophia", name: "Sophia", gender: "female", focus: "international" },
];

// Curated ElevenLabs voices picked specifically for this platform's Indian
// sales/support calls (not the full account-wide catalog) — names, voice_ids,
// and language/accent came directly from the ElevenLabs voice library.
const ELEVENLABS_VOICES: {
  id: string;
  name: string;
  gender: "male" | "female";
  focus: "hindi" | "indian-english";
}[] = [
  { id: "P3JECz9WQeXyyodBL3ZD", name: "Gargi — Regional E-com Customer…", gender: "female", focus: "hindi" },
  { id: "U6U9JrUgcMgeM9W1PYFd", name: "Sujit — Regional Outbound Sales Agent", gender: "male", focus: "hindi" },
  { id: "UbB19hYD8fvYxwJAVTY5", name: "Anika — Expressive & High Energy", gender: "female", focus: "hindi" },
  { id: "7LIHJn2g4SPvZIQniujs", name: "Ramesh P — Top Indian Sales Outbound", gender: "male", focus: "indian-english" },
  { id: "Ms9OTvWb99V6DwRHZn6q", name: "Monika Sogam — Deep and Clear", gender: "female", focus: "hindi" },
  { id: "hRclHnAGI1PGQgXUYKsd", name: "Samisha — Sweet & Warm SDR Voice", gender: "female", focus: "hindi" },
  { id: "zmh5xhBvMzqR4ZlXgcgL", name: "Monika Sogam — Lead Qualification", gender: "female", focus: "hindi" },
];

const ACCESS_ACCENT: Record<string, string> = {
  approved: "var(--success)",
  pending: "var(--warning)",
  locked: "var(--muted-foreground)",
};

const emptyForm: AgentCreate = {
  name: "",
  description: "",
  language: "hinglish",
  welcome_message: "",
  system_prompt: "",
  voice_id: "",
  voice_provider: "elevenlabs",
  llm_model: "llama-3.3-70b-versatile",
  llm_temperature: 0.7,
  max_call_duration_seconds: 600,
};

export default function Agents() {
  const { isAdmin } = useAuth();
  const agents = useAgents();
  const location = useLocation();
  const navigate = useNavigate();
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentTemplate | null>(null);
  const [prefillSystemPrompt, setPrefillSystemPrompt] = useState<string | undefined>(undefined);
  const [testCallAgent, setTestCallAgent] = useState<AgentTemplate | null>(null);
  const [requestCreationOpen, setRequestCreationOpen] = useState(false);

  // Arriving from the Prompt Library's "Use in this agent" button — open the
  // create-agent dialog pre-filled, then clear the nav state so a refresh or
  // back-navigation doesn't reopen it.
  useEffect(() => {
    const prefill = (location.state as { prefillSystemPrompt?: string } | null)?.prefillSystemPrompt;
    if (!prefill) return;
    setEditingAgent(null);
    setPrefillSystemPrompt(prefill);
    setEditorOpen(true);
    navigate(location.pathname, { replace: true, state: null });
  }, [location.state, location.pathname, navigate]);

  function openCreate() {
    setEditingAgent(null);
    setPrefillSystemPrompt(undefined);
    setEditorOpen(true);
  }
  function openEdit(agent: AgentTemplate) {
    setEditingAgent(agent);
    setPrefillSystemPrompt(undefined);
    setEditorOpen(true);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Agents"
        description="Manage AI agent templates for your team"
        actions={
          isAdmin ? (
            <Button variant="gradient" onClick={openCreate}>
              <Plus className="h-4 w-4" /> Create Agent
            </Button>
          ) : (
            <Button variant="outline" onClick={() => setRequestCreationOpen(true)}>
              <Plus className="h-4 w-4" /> Request new agent
            </Button>
          )
        }
      />

      {agents.isError ? (
        <ErrorBanner error={agents.error} onRetry={() => agents.refetch()} />
      ) : agents.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {[1, 2, 3, 4, 5, 6].map((i) => <Skeleton key={i} className="h-40 w-full" />)}
        </div>
      ) : agents.data && agents.data.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {agents.data.map((a) => (
            <AgentCard
              key={a.id}
              agent={a}
              isAdmin={isAdmin}
              onEdit={() => openEdit(a)}
              onTestCall={() => setTestCallAgent(a)}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={Bot}
          title="No AI agents yet"
          description={isAdmin ? "Create your first AI voice agent persona." : "Ask an admin to create an AI agent, or request a new one."}
          action={
            isAdmin ? (
              <Button variant="gradient" onClick={openCreate}>Create agent</Button>
            ) : (
              <Button variant="gradient" onClick={() => setRequestCreationOpen(true)}>Request new agent</Button>
            )
          }
        />
      )}

      <AgentEditorDialog
        open={editorOpen}
        onOpenChange={setEditorOpen}
        agent={editingAgent}
        initialSystemPrompt={prefillSystemPrompt}
      />
      <TestCallDialog agent={testCallAgent} onOpenChange={() => setTestCallAgent(null)} />
      <RequestCreationDialog open={requestCreationOpen} onOpenChange={setRequestCreationOpen} />
    </div>
  );
}

function AgentCard({
  agent,
  isAdmin,
  onEdit,
  onTestCall,
}: {
  agent: AgentTemplate;
  isAdmin: boolean;
  onEdit: () => void;
  onTestCall: () => void;
}) {
  const requestAccess = useRequestAgentAccess();
  const deleteAgent = useDeleteAgent();
  const canEdit = isAdmin || agent.can_edit;
  const canUse = agent.access_status === "approved";

  async function handleRequestAccess() {
    try {
      await requestAccess.mutateAsync(agent.id);
      toast.success("Access requested — an admin will review it");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't request access"));
    }
  }

  async function handleDelete() {
    if (!confirm(`Delete agent "${agent.name}"? This can't be undone.`)) return;
    try {
      await deleteAgent.mutateAsync(agent.id);
      toast.success("Agent deleted");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't delete agent"));
    }
  }

  const accent = ACCESS_ACCENT[agent.access_status] ?? ACCESS_ACCENT.locked;

  return (
    <div className="relative flex h-full flex-col overflow-hidden rounded-xl border border-border bg-card shadow-[var(--shadow-card)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow-elevated)]">
      <span className="absolute inset-x-0 top-0 h-1" style={{ backgroundColor: accent }} />
      <div className="flex flex-1 flex-col gap-3 p-3.5 pt-4">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[image:var(--gradient-primary)]">
            <Headset className="h-4 w-4 text-primary-foreground" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold leading-tight">{agent.name}</p>
            <p className="truncate text-[11px] text-muted-foreground">{agent.llm_model}</p>
          </div>
        </div>

        <div className="flex items-center justify-between text-xs">
          <AgentAccessBadge status={agent.access_status} />
          <span className="text-muted-foreground">{formatDate(agent.created_at)}</span>
        </div>

        {!canUse && !isAdmin && (
          <Button
            size="sm"
            variant="outline"
            className="w-full"
            onClick={handleRequestAccess}
            disabled={agent.access_status === "pending" || requestAccess.isPending}
          >
            {agent.access_status === "pending" ? <><Lock className="h-3.5 w-3.5" /> Pending</> : "Request access"}
          </Button>
        )}

        <div className="mt-auto flex gap-1.5 border-t border-border pt-2.5">
          <Button variant="outline" size="sm" className="flex-1" onClick={onEdit} disabled={!canEdit}>
            <Pencil className="h-3.5 w-3.5" /> Edit
          </Button>
          <Button variant="outline" size="icon" onClick={onTestCall} disabled={!canUse}>
            <Phone className="h-3.5 w-3.5" />
          </Button>
          {isAdmin && (
            <Button variant="outline" size="icon" onClick={handleDelete} disabled={deleteAgent.isPending}>
              <Trash2 className="h-3.5 w-3.5 text-destructive" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function AgentEditorDialog({
  open,
  onOpenChange,
  agent,
  initialSystemPrompt,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  agent: AgentTemplate | null;
  initialSystemPrompt?: string;
}) {
  const { isAdmin } = useAuth();
  const [form, setForm] = useState<AgentCreate>(agent ? toFormValues(agent) : emptyForm);
  const [optimizing, setOptimizing] = useState(false);
  const createAgent = useCreateAgent();
  const updateAgent = useUpdateAgent();
  const clonedVoices = useClonedVoices();
  // Cloned voices are ElevenLabs voice_ids too -- surfaced as a group inside
  // the same Voice dropdown below (not a second selector) so there's only
  // ever one place that can set voice_id, never two controls disagreeing
  // about what's actually selected.
  const readyClonedVoices = isAdmin
    ? (clonedVoices.data ?? []).filter((v) => v.status === "ready" && v.elevenlabs_voice_id)
    : [];

  // Whether the Voice field shows the cloned-voice picker or the regular
  // name/gender list -- exactly one is ever interactive at a time, so
  // there's only one place that can set voice_id.
  const [useClonedVoice, setUseClonedVoice] = useState(false);

  // AgentEditorDialog stays mounted permanently (only `open` toggles) so the
  // form must be re-synced here whenever it's opened for a different agent --
  // Radix's onOpenChange only fires for user-driven close events, never when
  // the parent flips `open` externally (which is how "Edit" opens this).
  useEffect(() => {
    if (open) {
      const base = agent ? toFormValues(agent) : emptyForm;
      setForm(initialSystemPrompt ? { ...base, system_prompt: initialSystemPrompt } : base);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, agent, initialSystemPrompt]);

  // Default the toggle to "on" when editing an agent whose saved voice_id is
  // actually one of this org's ready cloned voices. Watches clonedVoices.data
  // too since that query can still be loading the moment the dialog opens.
  useEffect(() => {
    if (!open) return;
    setUseClonedVoice(!!agent?.voice_id && readyClonedVoices.some((v) => v.elevenlabs_voice_id === agent.voice_id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, agent, clonedVoices.data]);

  function update<K extends keyof AgentCreate>(key: K, value: AgentCreate[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleOptimize() {
    if (!form.system_prompt?.trim()) {
      toast.error("Write a rough prompt first, then optimize it");
      return;
    }
    setOptimizing(true);
    try {
      const res = await agentsApi.optimizePrompt(form.system_prompt);
      update("system_prompt", res.data.optimized_prompt);
      toast.success("Prompt optimized");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't optimize prompt"));
    } finally {
      setOptimizing(false);
    }
  }

  async function handleSave() {
    if (!form.name?.trim()) {
      toast.error("Agent name is required");
      return;
    }
    try {
      if (agent) {
        await updateAgent.mutateAsync({ id: agent.id, data: form });
        toast.success("Agent updated");
      } else {
        await createAgent.mutateAsync(form);
        toast.success("Agent created");
      }
      onOpenChange(false);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't save agent"));
    }
  }

  const saving = createAgent.isPending || updateAgent.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{agent ? "Edit agent" : "Create agent"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Name</Label>
              <Input value={form.name} onChange={(e) => update("name", e.target.value)} placeholder="Enterprise Sales Agent" />
            </div>
            <div className="space-y-1.5">
              <Label>Language</Label>
              <Input value={form.language} onChange={(e) => update("language", e.target.value)} placeholder="hinglish" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Description</Label>
            <Input value={form.description} onChange={(e) => update("description", e.target.value)} placeholder="What is this agent for?" />
          </div>
          <div className="space-y-1.5">
            <Label>Welcome message</Label>
            <Textarea value={form.welcome_message} onChange={(e) => update("welcome_message", e.target.value)} placeholder="Namaste! Main Aniket bol raha hoon..." rows={2} />
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>System prompt</Label>
              <Button type="button" variant="ghost" size="sm" onClick={handleOptimize} disabled={optimizing}>
                {optimizing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                Optimize with AI
              </Button>
            </div>
            <Textarea value={form.system_prompt} onChange={(e) => update("system_prompt", e.target.value)} rows={6} placeholder="Describe how the agent should behave, what to pitch, objection handling..." />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Voice provider</Label>
              <Select
                value={form.voice_provider}
                onValueChange={(v) => {
                  // A voice_id from the old provider is meaningless (and can't be
                  // validated) for the new one -- clear it so a stale/mismatched
                  // pair can never get saved. See: previous agent voice_id vs
                  // voice_provider mismatch bug.
                  setForm((f) => ({ ...f, voice_provider: v, voice_id: "" }));
                }}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {VOICE_PROVIDERS.map((v) => <SelectItem key={v} value={v} className="capitalize">{v}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label>Voice</Label>
                {isAdmin && form.voice_provider === "elevenlabs" && (
                  <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    Use cloned voice
                    <Switch
                      checked={useClonedVoice}
                      onCheckedChange={(v) => {
                        // Whichever side you're leaving had voice_id pointed at
                        // its own list -- clear it so a stale value from one
                        // list can never get saved while the other is showing.
                        setUseClonedVoice(v);
                        update("voice_id", "");
                      }}
                    />
                  </label>
                )}
              </div>
              {form.voice_provider === "sarvam" ? (
                <Select value={form.voice_id} onValueChange={(v) => update("voice_id", v)}>
                  <SelectTrigger><SelectValue placeholder="Choose a voice…" /></SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectLabel>Hindi / Hinglish voices</SelectLabel>
                      {SARVAM_VOICES.filter((v) => v.focus === "hindi").map((v) => (
                        <SelectItem key={v.id} value={v.id}>
                          {v.name} <span className="text-muted-foreground">({v.gender})</span>
                        </SelectItem>
                      ))}
                    </SelectGroup>
                    <SelectGroup>
                      <SelectLabel>International (English-accented)</SelectLabel>
                      {SARVAM_VOICES.filter((v) => v.focus === "international").map((v) => (
                        <SelectItem key={v.id} value={v.id}>
                          {v.name} <span className="text-muted-foreground">({v.gender})</span>
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              ) : useClonedVoice ? (
                readyClonedVoices.length > 0 ? (
                  <Select value={form.voice_id} onValueChange={(v) => update("voice_id", v)}>
                    <SelectTrigger><SelectValue placeholder="Pick a cloned voice…" /></SelectTrigger>
                    <SelectContent>
                      {readyClonedVoices.map((v) => (
                        <SelectItem key={v.id} value={v.elevenlabs_voice_id ?? ""}>{v.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    {clonedVoices.isLoading ? "Loading cloned voices…" : (
                      <>
                        No cloned voices yet —{" "}
                        <Link to="/voice-cloning" className="text-primary hover:underline">
                          clone one from the Voice Cloning section
                        </Link>{" "}
                        to use it here.
                      </>
                    )}
                  </p>
                )
              ) : (
                <Select value={form.voice_id} onValueChange={(v) => update("voice_id", v)}>
                  <SelectTrigger><SelectValue placeholder="Choose a voice…" /></SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectLabel>Hindi voices</SelectLabel>
                      {ELEVENLABS_VOICES.filter((v) => v.focus === "hindi").map((v) => (
                        <SelectItem key={v.id} value={v.id}>
                          {v.name} <span className="text-muted-foreground">({v.gender})</span>
                        </SelectItem>
                      ))}
                    </SelectGroup>
                    <SelectGroup>
                      <SelectLabel>Indian-accented English</SelectLabel>
                      {ELEVENLABS_VOICES.filter((v) => v.focus === "indian-english").map((v) => (
                        <SelectItem key={v.id} value={v.id}>
                          {v.name} <span className="text-muted-foreground">({v.gender})</span>
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              )}
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>LLM model</Label>
              <Select value={form.llm_model} onValueChange={(v) => update("llm_model", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {LLM_MODELS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Max call duration (seconds)</Label>
              <Input type="number" value={form.max_call_duration_seconds} onChange={(e) => update("max_call_duration_seconds", Number(e.target.value))} />
            </div>
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>LLM temperature</Label>
              <span className="text-xs text-muted-foreground">{form.llm_temperature}</span>
            </div>
            <Slider
              value={[form.llm_temperature ?? 0.7]}
              min={0}
              max={1}
              step={0.05}
              onValueChange={([v]) => update("llm_temperature", v)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="gradient" onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            {agent ? "Save changes" : "Create agent"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function toFormValues(agent: AgentTemplate): AgentCreate {
  return {
    name: agent.name,
    description: agent.description ?? "",
    language: agent.language,
    welcome_message: agent.welcome_message,
    system_prompt: agent.system_prompt,
    voice_id: agent.voice_id,
    voice_provider: agent.voice_provider,
    llm_model: agent.llm_model,
    llm_temperature: agent.llm_temperature,
    max_call_duration_seconds: agent.max_call_duration_seconds,
  };
}

function TestCallDialog({ agent, onOpenChange }: { agent: AgentTemplate | null; onOpenChange: () => void }) {
  const [phone, setPhone] = useState("+91");
  const [trunkId, setTrunkId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const trunks = useMyTrunks();

  const trunkOptions = trunks.data ?? [];
  const selectedTrunk = trunkOptions.find((t) => t.id === trunkId) ?? trunkOptions[0];

  async function handleCall() {
    if (!agent) return;
    setLoading(true);
    try {
      await agentsApi.testCall(agent.id, phone, selectedTrunk?.id);
      toast.success("Test call started — it should ring shortly");
      onOpenChange();
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't start test call"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={!!agent} onOpenChange={(v) => !v && onOpenChange()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Test call — {agent?.name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label>From</Label>
          {trunks.isLoading ? (
            <Skeleton className="h-9 w-full" />
          ) : trunkOptions.length > 0 ? (
            <Select value={selectedTrunk?.id ?? ""} onValueChange={setTrunkId}>
              <SelectTrigger className="w-full"><SelectValue placeholder="Select a number..." /></SelectTrigger>
              <SelectContent>
                {trunkOptions.map((t) => (
                  <SelectItem key={t.id} value={t.id}>{t.caller_id} — {t.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <p className="text-sm text-muted-foreground">No connected numbers available to call from.</p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label>To</Label>
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91 98765 43210" />
        </div>
        <DialogFooter>
          <Button variant="gradient" onClick={handleCall} disabled={loading || !selectedTrunk}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Phone className="h-4 w-4" />}
            Place test call
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RequestCreationDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [form, setForm] = useState({
    agent_name: "",
    company_name: "",
    product_service: "",
    target_customers: "",
    key_points: "",
  });
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    if (!form.agent_name.trim() || !form.company_name.trim()) {
      toast.error("Agent name and company name are required");
      return;
    }
    if (file && file.size > 10 * 1024 * 1024) {
      toast.error("File must be 10MB or smaller");
      return;
    }
    setSubmitting(true);
    try {
      const fd = new FormData();
      Object.entries(form).forEach(([k, v]) => fd.append(k, v));
      if (file) fd.append("file", file);
      await agentsApi.requestCreation(fd);
      toast.success("Request submitted — an admin will follow up");
      onOpenChange(false);
      setForm({ agent_name: "", company_name: "", product_service: "", target_customers: "", key_points: "" });
      setFile(null);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't submit request"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Request a new AI agent</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Agent name</Label>
            <Input value={form.agent_name} onChange={(e) => setForm((f) => ({ ...f, agent_name: e.target.value }))} />
          </div>
          <div className="space-y-1.5">
            <Label>Company name</Label>
            <Input value={form.company_name} onChange={(e) => setForm((f) => ({ ...f, company_name: e.target.value }))} />
          </div>
          <div className="space-y-1.5">
            <Label>Product / service</Label>
            <Textarea rows={2} value={form.product_service} onChange={(e) => setForm((f) => ({ ...f, product_service: e.target.value }))} />
          </div>
          <div className="space-y-1.5">
            <Label>Target customers</Label>
            <Textarea rows={2} value={form.target_customers} onChange={(e) => setForm((f) => ({ ...f, target_customers: e.target.value }))} />
          </div>
          <div className="space-y-1.5">
            <Label>Key talking points</Label>
            <Textarea rows={3} value={form.key_points} onChange={(e) => setForm((f) => ({ ...f, key_points: e.target.value }))} />
          </div>
          <div className="space-y-1.5">
            <Label>Reference file (optional, max 10MB)</Label>
            <Input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="gradient" onClick={handleSubmit} disabled={submitting}>
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            Submit request
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
