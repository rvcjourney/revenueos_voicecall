import { createFileRoute } from "@tanstack/react-router";
import { useAuth } from "@/lib/auth";
import { useState, useEffect, useRef } from "react";
import { toast } from "sonner";
import { voices } from "@/lib/mock-data";
import { agentsApi, callsApi, type AgentOut, type AgentCreate, type AgentCreationRequestOut } from "@/lib/api";
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
  Plus, Bot, Edit, Trash2, Sparkles, Loader2, CheckCircle, Phone, PhoneCall, PhoneOff,
  Lock, Unlock, Clock, Send,
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

// ── Agent Request Form — defined before Agents() so JSX can reference it ─────

function AgentRequestForm({ onClose, onSubmitted }: { onClose: () => void; onSubmitted: () => void }) {
  const [form, setForm] = useState({
    agent_name: "", company_name: "", product_service: "", target_customers: "", key_points: "",
  });
  const [file, setFile]      = useState<File | null>(null);
  const [submitting, setSub] = useState(false);
  const fileRef              = useRef<HTMLInputElement>(null);

  function setF(k: keyof typeof form, v: string) { setForm(f => ({ ...f, [k]: v })); }

  async function handleSubmit() {
    if (!form.agent_name.trim() || !form.company_name.trim() || !form.product_service.trim()
        || !form.target_customers.trim() || !form.key_points.trim()) {
      toast.error("Please fill all fields"); return;
    }
    setSub(true);
    try {
      const fd = new FormData();
      fd.append("agent_name",       form.agent_name.trim());
      fd.append("company_name",     form.company_name.trim());
      fd.append("product_service",  form.product_service.trim());
      fd.append("target_customers", form.target_customers.trim());
      fd.append("key_points",       form.key_points.trim());
      if (file) fd.append("file", file);
      await agentsApi.requestCreation(fd);
      onSubmitted();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to submit request");
    } finally {
      setSub(false);
    }
  }

  return (
    <div className="rounded-xl bg-card border border-primary/30 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-base flex items-center gap-2">
          <Bot className="h-4 w-4 text-primary" /> Request a New AI Agent
        </h2>
        <Button variant="ghost" size="sm" onClick={onClose}>✕</Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Fill in your company details. The admin will create a customized AI agent for your campaigns.
      </p>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Agent / Campaign Name *</Label>
          <Input value={form.agent_name} onChange={e => setF("agent_name", e.target.value)}
            placeholder="e.g. Sales Bot for B2B" />
        </div>
        <div className="space-y-1.5">
          <Label>Company Name *</Label>
          <Input value={form.company_name} onChange={e => setF("company_name", e.target.value)}
            placeholder="e.g. Baba Valves Pvt Ltd" />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label>What do you sell? *</Label>
        <Textarea rows={2} value={form.product_service} onChange={e => setF("product_service", e.target.value)}
          placeholder="e.g. Industrial valves for manufacturing plants — gate valves, ball valves, check valves" />
      </div>

      <div className="space-y-1.5">
        <Label>Who are your target customers? *</Label>
        <Textarea rows={2} value={form.target_customers} onChange={e => setF("target_customers", e.target.value)}
          placeholder="e.g. Purchase managers at factories, plant engineers in Gujarat & Maharashtra" />
      </div>

      <div className="space-y-1.5">
        <Label>Key selling points / talking points *</Label>
        <Textarea rows={3} value={form.key_points} onChange={e => setF("key_points", e.target.value)}
          placeholder="e.g. ISI certified, 5-year warranty, bulk discounts above 500 units, free site visit" />
      </div>

      <div className="space-y-1.5">
        <Label>Product catalogue / brochure <span className="text-muted-foreground text-xs">(optional — PDF, Word, image)</span></Label>
        <div className="border border-dashed border-border rounded-lg p-4 flex items-center gap-3 cursor-pointer hover:border-primary/50 transition-colors"
          onClick={() => fileRef.current?.click()}>
          <input ref={fileRef} type="file" className="hidden" accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg"
            onChange={e => setFile(e.target.files?.[0] ?? null)} />
          {file ? (
            <div className="flex items-center gap-2 text-sm">
              <CheckCircle className="h-4 w-4 text-green-400" />
              <span>{file.name}</span>
              <span className="text-muted-foreground text-xs">({(file.size / 1024).toFixed(0)} KB)</span>
              <Button variant="ghost" size="sm" className="h-6 text-xs text-destructive ml-2"
                onClick={e => { e.stopPropagation(); setFile(null); }}>Remove</Button>
            </div>
          ) : (
            <span className="text-sm text-muted-foreground">Click to upload a file (max 10MB)</span>
          )}
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button className="bg-gradient-primary text-white" onClick={handleSubmit} disabled={submitting}>
          {submitting
            ? <><Loader2 className="h-4 w-4 animate-spin" /> Submitting…</>
            : <><Send className="h-4 w-4" /> Submit Request</>}
        </Button>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
function AccessBadge({ status }: { status: string }) {
  if (status === "approved") return (
    <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-green-500/15 text-green-400 border border-green-500/30">
      <Unlock className="h-2.5 w-2.5" /> Available
    </span>
  );
  if (status === "pending") return (
    <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30">
      <Clock className="h-2.5 w-2.5" /> Pending
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-surface-2 text-muted-foreground border border-border">
      <Lock className="h-2.5 w-2.5" /> Locked
    </span>
  );
}

function Agents() {
  const { isAdmin } = useAuth();
  const [agents, setAgents]                 = useState<AgentOut[]>([]);
  const [myRequests, setMyRequests]         = useState<AgentCreationRequestOut[]>([]);
  const [loading, setLoading]               = useState(true);
  const [requesting, setRequesting]         = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [showModal, setShowModal]           = useState(false);
  const [editTarget, setEditTarget]         = useState<AgentOut | null>(null);
  const [testCallAgent, setTestCallAgent]   = useState<AgentOut | null>(null);

  function loadAgents() {
    agentsApi.list()
      .then((r) => setAgents(r.data.items))
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  function loadMyRequests() {
    if (!isAdmin) {
      agentsApi.myCreationRequests()
        .then((r) => setMyRequests(r.data))
        .catch(() => {});
    }
  }

  useEffect(() => { loadAgents(); loadMyRequests(); }, [isAdmin]);

  const handleSaved = (agent: AgentOut) => {
    setAgents((prev) => {
      const idx = prev.findIndex((a) => a.id === agent.id);
      return idx >= 0 ? prev.map((a) => (a.id === agent.id ? agent : a)) : [agent, ...prev];
    });
    setShowModal(false);
    setEditTarget(null);
  };

  const handleSavedAndTest = (agent: AgentOut) => {
    setAgents((prev) => {
      const idx = prev.findIndex((a) => a.id === agent.id);
      return idx >= 0 ? prev.map((a) => (a.id === agent.id ? agent : a)) : [agent, ...prev];
    });
    setShowModal(false);
    setEditTarget(null);
    setTestCallAgent(agent);
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this agent template?")) return;
    await agentsApi.delete(id);
    setAgents((prev) => prev.filter((a) => a.id !== id));
  };

  const handleRequestAccess = async (agentId: string) => {
    setRequesting(agentId);
    try {
      await agentsApi.requestAccess(agentId);
      toast.success("Access request sent! Your admin will review it.");
      loadAgents(); // refresh access_status
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to request access");
    } finally {
      setRequesting(null);
    }
  };

  const openCreate   = () => { setEditTarget(null); setShowModal(true); };
  const openEdit     = (a: AgentOut) => { setEditTarget(a); setShowModal(true); };
  const openTestCall = (a: AgentOut) => setTestCallAgent(a);

  return (
    <div className="space-y-6 max-w-[1500px]">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">AI Agents</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {isAdmin ? "Manage AI agent templates for your team" : "Request a new agent or access an existing one for your campaigns"}
          </p>
        </div>
        {isAdmin && (
          <Button className="bg-gradient-primary text-white shadow-glow" onClick={openCreate}>
            <Plus className="h-4 w-4" /> Create Agent
          </Button>
        )}
        {!isAdmin && (
          <Button className="bg-gradient-primary text-white shadow-glow" onClick={() => setShowCreateForm(true)}>
            <Send className="h-4 w-4" /> Request New Agent
          </Button>
        )}
      </div>

      {/* Member: Request New Agent Form */}
      {!isAdmin && showCreateForm && (
        <AgentRequestForm
          onClose={() => setShowCreateForm(false)}
          onSubmitted={() => { setShowCreateForm(false); loadMyRequests(); toast.success("Request submitted! Your admin will create the agent."); }}
        />
      )}

      {/* Member: My Submitted Requests */}
      {!isAdmin && myRequests.length > 0 && (
        <div className="rounded-xl bg-card border border-border p-5">
          <h2 className="font-semibold text-sm mb-3 flex items-center gap-2">
            <Clock className="h-4 w-4 text-amber-400" /> My Agent Requests
          </h2>
          <div className="space-y-2">
            {myRequests.map((r) => (
              <div key={r.id} className="flex items-center justify-between rounded-lg bg-surface-2/50 px-4 py-3 text-sm">
                <div>
                  <span className="font-medium">{r.agent_name}</span>
                  <span className="text-muted-foreground ml-2 text-xs">— {r.company_name}</span>
                </div>
                <div className="flex items-center gap-3">
                  {r.has_file && <span className="text-[10px] text-muted-foreground border border-border px-2 py-0.5 rounded">{r.file_name}</span>}
                  {r.status === "pending" ? (
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30">
                      <Clock className="h-2.5 w-2.5" /> Pending
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-green-500/15 text-green-400 border border-green-500/30">
                      <CheckCircle className="h-2.5 w-2.5" /> Done
                    </span>
                  )}
                  {r.admin_notes && <span className="text-xs text-muted-foreground italic">"{r.admin_notes}"</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Grid */}
      {loading ? (
        <div className="flex items-center justify-center h-40 text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin mr-2" /> Loading agents…
        </div>
      ) : agents.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-60 text-muted-foreground gap-3 border border-dashed border-border rounded-xl">
          <Bot className="h-12 w-12 opacity-30" />
          <p className="text-sm">{isAdmin ? "No agents yet. Create your first agent template." : "No agent templates available yet. Ask your admin to create one."}</p>
          {isAdmin && <Button variant="outline" onClick={openCreate}><Plus className="h-4 w-4" /> Create Agent</Button>}
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map((a) => {
            const voice = voices.find((v) => v.id === a.voice_id) ?? voices[0];
            const isLocked = !isAdmin && a.access_status !== "approved";
            return (
              <div
                key={a.id}
                className={`rounded-xl bg-card border p-5 transition-colors flex flex-col ${
                  isLocked ? "border-border opacity-80" : "border-border hover:border-primary/40"
                }`}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className={`h-12 w-12 rounded-lg grid place-items-center text-white flex-shrink-0 ${
                    isLocked ? "bg-surface-2" : "bg-gradient-primary"
                  }`}>
                    {isLocked ? <Lock className="h-5 w-5 text-muted-foreground" /> : <Bot className="h-6 w-6" />}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2 py-0.5 rounded bg-surface-3 text-muted-foreground">{a.language}</span>
                    {!isAdmin && <AccessBadge status={a.access_status ?? "locked"} />}
                  </div>
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
                  {isAdmin ? (
                    <>
                      <Button variant="outline" size="sm" className="flex-1" onClick={() => openEdit(a)}>
                        <Edit className="h-3 w-3" /> Edit
                      </Button>
                      <Button
                        variant="outline" size="sm"
                        className="text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10 hover:text-emerald-300"
                        title="Test Call" onClick={() => openTestCall(a)}
                      >
                        <Phone className="h-3 w-3" />
                      </Button>
                      <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive" onClick={() => handleDelete(a.id)}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </>
                  ) : a.access_status === "approved" ? (
                    <div className="flex items-center gap-2 w-full">
                      <div className="flex items-center gap-1.5 text-xs text-green-400 font-medium flex-1">
                        <CheckCircle className="h-3.5 w-3.5" /> Ready to use
                      </div>
                      {a.can_edit && (
                        <Button variant="outline" size="sm" onClick={() => openEdit(a)}>
                          <Edit className="h-3 w-3" /> Edit
                        </Button>
                      )}
                    </div>
                  ) : a.access_status === "pending" ? (
                    <div className="flex items-center gap-1.5 text-xs text-amber-400 font-medium">
                      <Clock className="h-3.5 w-3.5" /> Waiting for admin approval…
                    </div>
                  ) : (
                    <Button
                      size="sm"
                      className="flex-1 bg-gradient-primary text-white"
                      disabled={requesting === a.id}
                      onClick={() => handleRequestAccess(a.id)}
                    >
                      {requesting === a.id
                        ? <><Loader2 className="h-3 w-3 animate-spin" /> Requesting…</>
                        : <><Send className="h-3 w-3" /> Request Access</>}
                    </Button>
                  )}
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
          onSavedAndTest={handleSavedAndTest}
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
  onSavedAndTest?: (agent: AgentOut) => void;
  onClose: () => void;
}

function AgentModal({ initial, onSaved, onSavedAndTest, onClose }: AgentModalProps) {
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

  const handleSave = async (andTest = false) => {
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
      if (andTest && onSavedAndTest) {
        onSavedAndTest(agent);
      } else {
        onSaved(agent);
      }
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
                <SelectItem value="chatterbox">
                  Chatterbox (self-hosted GPU) — Test only
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
          {onSavedAndTest && (
            <Button
              variant="outline"
              className="text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10 hover:text-emerald-300"
              onClick={() => handleSave(true)}
              disabled={saving || !form.name.trim()}
            >
              {saving ? <><Loader2 className="h-4 w-4 animate-spin" /> Saving…</> : <><Phone className="h-4 w-4" /> Save & Test Call</>}
            </Button>
          )}
          <Button
            className="bg-gradient-primary text-white shadow-glow"
            onClick={() => handleSave(false)}
            disabled={saving || !form.name.trim()}
          >
            {saving ? <><Loader2 className="h-4 w-4 animate-spin" /> Saving…</> : isEdit ? "Save Changes" : "Create Agent"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
