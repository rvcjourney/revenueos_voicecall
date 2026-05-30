import { createFileRoute } from "@tanstack/react-router";
import { useState, useEffect, useRef } from "react";
import { toast } from "sonner";
import { voices } from "@/lib/mock-data";
import { agentsApi, callsApi, type AgentOut, type AgentCreate } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import {
  Plus, Bot, Edit, Copy, Trash2, Sparkles, Loader2, CheckCircle, Phone, PhoneCall, PhoneOff,
} from "lucide-react";

export const Route = createFileRoute("/_authed/agents")({
  head: () => ({ meta: [{ title: "AI Agents — MOTMVoice" }] }),
  component: Agents,
});

// ── Default form state ────────────────────────────────────────────────────────
const EMPTY_FORM: AgentCreate = {
  name: "",
  description: "",
  language: "Hinglish",
  welcome_message: "",
  system_prompt: "",
  voice_id: voices[0].id,
  voice_provider: "elevenlabs",
  llm_model: "llama-3.3-70b-versatile",
  llm_temperature: 0.7,
  max_call_duration_seconds: 600,
};

// ── Main component ────────────────────────────────────────────────────────────
function Agents() {
  const [agents, setAgents]         = useState<AgentOut[]>([]);
  const [loading, setLoading]       = useState(true);
  const [showModal, setShowModal]   = useState(false);
  const [editTarget, setEditTarget] = useState<AgentOut | null>(null);
  const [testCallAgent, setTestCallAgent] = useState<AgentOut | null>(null);

  useEffect(() => {
    agentsApi.list()
      .then((r) => setAgents(r.data.items))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleSaved = (agent: AgentOut) => {
    setAgents((prev) => {
      const idx = prev.findIndex((a) => a.id === agent.id);
      return idx >= 0
        ? prev.map((a) => (a.id === agent.id ? agent : a))
        : [agent, ...prev];
    });
    setShowModal(false);
    setEditTarget(null);
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this agent template?")) return;
    await agentsApi.delete(id);
    setAgents((prev) => prev.filter((a) => a.id !== id));
  };

  const openCreate    = () => { setEditTarget(null); setShowModal(true); };
  const openEdit      = (a: AgentOut) => { setEditTarget(a); setShowModal(true); };
  const openTestCall  = (a: AgentOut) => setTestCallAgent(a);

  return (
    <div className="space-y-6 max-w-[1500px]">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">AI Agents</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Reusable agent templates with AI-optimized system prompts
          </p>
        </div>
        <Button className="bg-gradient-primary text-white shadow-glow" onClick={openCreate}>
          <Plus className="h-4 w-4" /> Create Agent
        </Button>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="flex items-center justify-center h-40 text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin mr-2" /> Loading agents…
        </div>
      ) : agents.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-60 text-muted-foreground gap-3 border border-dashed border-border rounded-xl">
          <Bot className="h-12 w-12 opacity-30" />
          <p className="text-sm">No agents yet. Create your first agent template.</p>
          <Button variant="outline" onClick={openCreate}><Plus className="h-4 w-4" /> Create Agent</Button>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map((a) => {
            const voice = voices.find((v) => v.id === a.voice_id) ?? voices[0];
            return (
              <div key={a.id} className="rounded-xl bg-card border border-border p-5 hover:border-primary/40 transition-colors flex flex-col">
                <div className="flex items-start justify-between mb-3">
                  <div className="h-12 w-12 rounded-lg bg-gradient-primary grid place-items-center text-white flex-shrink-0">
                    <Bot className="h-6 w-6" />
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded bg-surface-3 text-muted-foreground">{a.language}</span>
                </div>
                <h3 className="font-semibold">{a.name}</h3>
                {a.description && (
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{a.description}</p>
                )}
                <div className="mt-3 text-xs text-muted-foreground space-y-1 flex-1">
                  <div>Voice: <span className="text-foreground">{voice.name}</span></div>
                  <div>Model: <span className="text-foreground">{a.llm_model.split("/").pop()}</span></div>
                  <div>Temperature: <span className="text-foreground">{a.llm_temperature}</span></div>
                  <div className="text-[11px] opacity-60 mt-1">
                    Created {new Date(a.created_at).toLocaleDateString()}
                  </div>
                </div>
                <div className="mt-4 flex gap-2">
                  <Button variant="outline" size="sm" className="flex-1" onClick={() => openEdit(a)}>
                    <Edit className="h-3 w-3" /> Edit
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10 hover:text-emerald-300"
                    title="Test Call"
                    onClick={() => openTestCall(a)}
                  >
                    <Phone className="h-3 w-3" />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => {
                    navigator.clipboard.writeText(a.system_prompt);
                  }}>
                    <Copy className="h-3 w-3" />
                  </Button>
                  <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive" onClick={() => handleDelete(a.id)}>
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create / Edit Modal */}
      {showModal && (
        <AgentModal
          initial={editTarget}
          onSaved={handleSaved}
          onClose={() => { setShowModal(false); setEditTarget(null); }}
        />
      )}

      {/* Test Call Dialog */}
      {testCallAgent && (
        <TestCallDialog
          agent={testCallAgent}
          onClose={() => setTestCallAgent(null)}
        />
      )}
    </div>
  );
}

// ── Test Call Dialog ──────────────────────────────────────────────────────────

type CallPhase = "idle" | "calling" | "connected" | "ended" | "no_answer" | "failed";

interface TestCallDialogProps {
  agent: AgentOut;
  onClose: () => void;
}

function TestCallDialog({ agent, onClose }: TestCallDialogProps) {
  const [phone, setPhone]       = useState("+91 ");
  const [phase, setPhase]       = useState<CallPhase>("idle");
  const [callId, setCallId]     = useState<string | null>(null);
  const [outcome, setOutcome]   = useState<string | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [error, setError]       = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  useEffect(() => () => stopPolling(), []);

  const startCall = async () => {
    const clean = phone.trim().replace(/\s/g, "");
    if (clean.length < 8) { setError("Enter a valid phone number."); return; }
    setError("");
    setPhase("calling");
    setOutcome(null);
    setDuration(null);

    try {
      const res = await agentsApi.testCall(agent.id, clean);
      const id  = res.data.call_id;
      setCallId(id);

      // Poll GET /api/calls/{id} every 3 s for status
      pollRef.current = setInterval(async () => {
        try {
          const r = await callsApi.get(id);
          const s = r.data.status;
          if (s === "connected")  setPhase("connected");
          if (s === "no_answer")  { setPhase("no_answer"); stopPolling(); }
          if (s === "failed")     { setPhase("failed");    stopPolling(); }
          if (s === "completed") {
            setPhase("ended");
            setOutcome(r.data.outcome ?? null);
            setDuration(r.data.duration_seconds ?? null);
            stopPolling();
          }
        } catch { /* ignore transient errors */ }
      }, 3000);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to initiate call. Please try again.");
      setPhase("idle");
    }
  };

  const phaseLabel: Record<CallPhase, string> = {
    idle:      "",
    calling:   "Dialling…",
    connected: "Connected — call in progress",
    ended:     "Call ended",
    no_answer: "Not answered",
    failed:    "Call failed",
  };

  const outcomeLabels: Record<string, string> = {
    interested:         "✅ Interested",
    not_interested:     "❌ Not interested",
    callback_requested: "📅 Callback requested",
    wrong_number:       "⚠️ Wrong number",
    do_not_call:        "🚫 Do not call",
    voicemail:          "📬 Voicemail",
    no_answer:          "📵 No answer",
    pending:            "⏳ Processing…",
  };

  const isActive = phase === "calling" || phase === "connected";

  return (
    <Dialog open onOpenChange={(o) => { if (!o && !isActive) onClose(); }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <PhoneCall className="h-4 w-4 text-emerald-400" />
            Test Call — {agent.name}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <p className="text-xs text-muted-foreground">
            This places a real outbound call to the number you enter, using this agent's voice, prompt, and settings.
          </p>

          <div className="space-y-1.5">
            <Label>Phone Number</Label>
            <Input
              placeholder="+91 98765 43210"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              disabled={isActive}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          {/* Status area */}
          {phase !== "idle" && (
            <div className={`rounded-lg border px-4 py-3 text-sm flex items-center gap-3 ${
              phase === "connected"  ? "border-emerald-500/40 bg-emerald-500/8 text-emerald-300" :
              phase === "ended"      ? "border-primary/30 bg-primary/5 text-foreground" :
              phase === "no_answer"  ? "border-orange-500/40 bg-orange-500/8 text-orange-300" :
              phase === "failed"     ? "border-destructive/40 bg-destructive/8 text-destructive" :
              "border-border bg-surface-1 text-muted-foreground"
            }`}>
              {isActive
                ? <Loader2 className="h-4 w-4 animate-spin flex-shrink-0" />
                : phase === "ended"
                  ? <CheckCircle className="h-4 w-4 text-emerald-400 flex-shrink-0" />
                  : <PhoneOff className="h-4 w-4 flex-shrink-0" />
              }
              <div>
                <div className="font-medium">{phaseLabel[phase]}</div>
                {phase === "ended" && outcome && (
                  <div className="text-xs mt-0.5 text-muted-foreground">
                    Outcome: {outcomeLabels[outcome] ?? outcome}
                    {duration != null && ` · ${Math.round(duration / 60)}m ${duration % 60}s`}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose} disabled={isActive}>
            {isActive ? "Call in progress…" : "Close"}
          </Button>
          {phase === "idle" || phase === "ended" || phase === "no_answer" || phase === "failed" ? (
            <Button
              className="bg-gradient-primary text-white shadow-glow"
              onClick={startCall}
              disabled={isActive}
            >
              <Phone className="h-4 w-4" />
              {phase === "idle" ? "Start Test Call" : "Call Again"}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


// ── Agent Create/Edit Modal ───────────────────────────────────────────────────
interface AgentModalProps {
  initial: AgentOut | null;
  onSaved: (agent: AgentOut) => void;
  onClose: () => void;
}

function AgentModal({ initial, onSaved, onClose }: AgentModalProps) {
  const isEdit = !!initial;

  const [form, setForm] = useState<AgentCreate>(() =>
    initial
      ? {
          name: initial.name,
          description: initial.description ?? "",
          language: initial.language,
          welcome_message: initial.welcome_message,
          system_prompt: initial.system_prompt,
          voice_id: initial.voice_id,
          voice_provider: initial.voice_provider ?? "elevenlabs",
          llm_model: initial.llm_model,
          llm_temperature: initial.llm_temperature,
          max_call_duration_seconds: initial.max_call_duration_seconds,
        }
      : { ...EMPTY_FORM }
  );

  const [rawInput,        setRawInput]        = useState("");
  const [generating,      setGenerating]      = useState(false);
  const [generateDone,    setGenerateDone]    = useState(false);
  const [generateError,   setGenerateError]   = useState("");
  const [saving,          setSaving]          = useState(false);
  const [activeTab,       setActiveTab]       = useState<"generate" | "manual">("generate");

  const set = (key: keyof AgentCreate, val: unknown) =>
    setForm((prev) => ({ ...prev, [key]: val }));

  const handleGenerate = async () => {
    if (!rawInput.trim() || rawInput.trim().length < 30) {
      setGenerateError("Please provide more detail — at least a few sentences about your company and products.");
      return;
    }
    setGenerateError("");
    setGenerating(true);
    setGenerateDone(false);
    try {
      const res = await agentsApi.optimizePrompt(rawInput);
      set("system_prompt", res.data.optimized_prompt);
      setGenerateDone(true);
      // Switch to manual tab so user can review & edit the prompt
      setActiveTab("manual");
    } catch (e: any) {
      setGenerateError(e?.response?.data?.detail ?? "Failed to generate prompt. Please try again.");
    } finally {
      setGenerating(false);
    }
  };

  const handleSave = async () => {
    if (!form.name.trim()) { toast.error("Agent name is required"); return; }
    setSaving(true);
    try {
      // Normalize language to lowercase — backend enum expects "hinglish" not "Hinglish"
      const payload = { ...form, language: (form.language ?? "hinglish").toLowerCase() };
      let agent: AgentOut;
      if (isEdit && initial) {
        const res = await agentsApi.update(initial.id, payload);
        agent = res.data;
      } else {
        const res = await agentsApi.create(payload);
        agent = res.data;
      }
      toast.success(isEdit ? "Agent updated" : "Agent created");
      onSaved(agent);
    } catch (e: any) {
      const detail = e?.response?.data?.detail ?? e?.message ?? "Save failed";
      toast.error(typeof detail === "string" ? detail : JSON.stringify(detail));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Agent" : "Create New Agent"}</DialogTitle>
        </DialogHeader>

        <div className="space-y-5 py-2">

          {/* Basic info */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Agent Name *</Label>
              <Input
                placeholder="e.g. Rajesh — Sales Engineer"
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Language</Label>
              <Select value={form.language} onValueChange={(v) => set("language", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="Hinglish">Hinglish</SelectItem>
                  <SelectItem value="Hindi">Hindi</SelectItem>
                  <SelectItem value="English">English</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Description <span className="text-muted-foreground text-xs">(optional)</span></Label>
            <Input
              placeholder="e.g. Industrial fan sales — B2B outbound"
              value={form.description ?? ""}
              onChange={(e) => set("description", e.target.value)}
            />
          </div>

          {/* System prompt tabs */}
          <div className="space-y-3">
            <div className="flex gap-2 border-b border-border">
              <button
                className={`pb-2 px-1 text-sm font-medium transition-colors border-b-2 ${activeTab === "generate" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                onClick={() => setActiveTab("generate")}
              >
                <span className="flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5" /> AI Generate Prompt
                </span>
              </button>
              <button
                className={`pb-2 px-1 text-sm font-medium transition-colors border-b-2 ${activeTab === "manual" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                onClick={() => setActiveTab("manual")}
              >
                Manual / Edit Prompt
              </button>
            </div>

            {/* ── Generate tab ── */}
            {activeTab === "generate" && (
              <div className="space-y-3">
                <div className="rounded-lg bg-primary/5 border border-primary/20 px-4 py-3 text-sm text-muted-foreground">
                  <p className="font-medium text-foreground mb-1">How it works</p>
                  Paste your raw company knowledge below — products, services, certifications, target customers, what you want the agent to say. Our AI will structure it into a perfect voice agent prompt automatically.
                </div>
                <div className="space-y-1.5">
                  <Label>Raw Company Knowledge & Sales Goal</Label>
                  <Textarea
                    placeholder={`Example:\n\nCompany: ABC Pumps Pvt Ltd, Pune, Maharashtra\nAgent name: Suresh, Sales Executive, 10 years experience\nProducts: centrifugal pumps, submersible pumps, booster pumps\nTarget: manufacturing plants, water treatment, pharma factories\nGoal: generate leads, collect WhatsApp numbers, book demo calls\nKey strength: 24/7 service, ISO certified, delivery in 2 weeks\nWebsite: www.abcpumps.com, Phone: +91 9800000000`}
                    className="min-h-[200px] font-mono text-xs"
                    value={rawInput}
                    onChange={(e) => setRawInput(e.target.value)}
                  />
                </div>
                {generateError && (
                  <p className="text-sm text-destructive">{generateError}</p>
                )}
                {generateDone && (
                  <p className="text-sm text-emerald-500 flex items-center gap-1.5">
                    <CheckCircle className="h-4 w-4" /> Prompt generated! Review and edit it in the "Manual / Edit Prompt" tab.
                  </p>
                )}
                <Button
                  className="bg-gradient-primary text-white shadow-glow w-full"
                  onClick={handleGenerate}
                  disabled={generating}
                >
                  {generating ? (
                    <><Loader2 className="h-4 w-4 animate-spin" /> Generating prompt…</>
                  ) : (
                    <><Sparkles className="h-4 w-4" /> Generate Optimized Prompt</>
                  )}
                </Button>
              </div>
            )}

            {/* ── Manual/Edit tab ── */}
            {activeTab === "manual" && (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label>System Prompt</Label>
                    <span className="text-xs text-muted-foreground">{form.system_prompt?.length ?? 0} chars</span>
                  </div>
                  <Textarea
                    placeholder="Paste or write the system prompt here, or use the AI Generate tab above."
                    className="min-h-[300px] font-mono text-xs"
                    value={form.system_prompt ?? ""}
                    onChange={(e) => set("system_prompt", e.target.value)}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Welcome message */}
          <div className="space-y-1.5">
            <Label>Welcome Message</Label>
            <Input
              placeholder='e.g. "Namaste sir! Main Rajesh bol raha hoon, Multivent Engineers se…"'
              value={form.welcome_message ?? ""}
              onChange={(e) => set("welcome_message", e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              This is the very first line the agent speaks — before the LLM kicks in.
            </p>
          </div>

          {/* TTS Provider */}
          <div className="space-y-1.5">
            <Label>TTS Provider</Label>
            <Select
              value={form.voice_provider ?? "elevenlabs"}
              onValueChange={(v) => {
                set("voice_provider", v);
                // Auto-select the first voice for the chosen provider
                const first = voices.find((vx) => vx.provider === v);
                if (first) set("voice_id", first.id);
              }}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="elevenlabs">
                  ElevenLabs — High quality, natural Indian voices
                </SelectItem>
                <SelectItem value="cartesia">
                  Cartesia Sonic 3.5 — Ultra-low latency (~150ms)
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Voice + Model */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Voice</Label>
              <Select value={form.voice_id} onValueChange={(v) => set("voice_id", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {voices
                    .filter((v) => v.provider === (form.voice_provider ?? "elevenlabs"))
                    .map((v) => (
                      <SelectItem key={v.id} value={v.id}>
                        {v.name} — {v.desc}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>LLM Model</Label>
              <Select value={form.llm_model} onValueChange={(v) => set("llm_model", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="llama-3.3-70b-versatile">llama-3.3-70b-versatile (Recommended)</SelectItem>
                  <SelectItem value="llama-3.1-8b-instant">llama-3.1-8b-instant (Fastest)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Temperature */}
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <Label>Temperature</Label>
              <span className="text-sm font-mono text-muted-foreground">{form.llm_temperature}</span>
            </div>
            <Slider
              min={0.1} max={1.0} step={0.05}
              value={[form.llm_temperature ?? 0.7]}
              onValueChange={([v]) => set("llm_temperature", v)}
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>0.1 — Very consistent</span>
              <span>0.7 — Natural sales</span>
              <span>1.0 — Creative/varied</span>
            </div>
          </div>

        </div>

        <DialogFooter className="gap-2 pt-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            className="bg-gradient-primary text-white shadow-glow"
            onClick={handleSave}
            disabled={saving || !form.name.trim()}
          >
            {saving ? <><Loader2 className="h-4 w-4 animate-spin" /> Saving…</> : isEdit ? "Save Changes" : "Create Agent"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
