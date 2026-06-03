import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Slider } from "@/components/ui/slider";
import {
  Check, Upload, FileSpreadsheet, ChevronLeft, ChevronRight,
  Rocket, Save, X, Bot, Loader2, Plus,
} from "lucide-react";
import { voices } from "@/lib/mock-data";
import { agentsApi, campaignsApi, type AgentOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";

export const Route = createFileRoute("/_authed/campaigns/new")({
  head: () => ({ meta: [{ title: "New Campaign — MOTMVoice" }] }),
  component: NewCampaign,
});

const stepsList = [
  { n: 1, title: "Basics",        desc: "Name & goal"    },
  { n: 2, title: "Contacts",      desc: "Upload CSV"     },
  { n: 3, title: "Select Agent",  desc: "Choose agent"   },
  { n: 4, title: "Schedule",      desc: "Launch"         },
];

// Map frontend display goals → backend enum values
const GOAL_MAP: Record<string, string> = {
  "Lead Generation": "lead_generation",
  "Product Demo":    "announcement",
  "Follow-up":       "follow_up",
  "Cold Outreach":   "lead_generation",
};

// Map frontend display days → backend short codes
const DAY_CODE: Record<string, string> = {
  Mon: "mon", Tue: "tue", Wed: "wed", Thu: "thu", Fri: "fri", Sat: "sat", Sun: "sun",
};

function NewCampaign() {
  const { isAdmin } = useAuth();
  const [step, setStep]           = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const navigate                  = useNavigate();

  // ── Step 1: Basics ──────────────────────────────────────────────────────────
  const [basics, setBasics] = useState({ name: "", description: "", goal: "Lead Generation" });

  // ── Step 2: Contacts ────────────────────────────────────────────────────────
  const [contactFile, setContactFile] = useState<File | null>(null);
  const [fileInfo, setFileInfo]       = useState<{ name: string; size: number; rows: number } | null>(null);

  // ── Step 3: Agent selection ─────────────────────────────────────────────────
  const [agents, setAgents]               = useState<AgentOut[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("");

  useEffect(() => {
    agentsApi.list()
      .then(({ data }) => {
        // Members can only use agents they have approved access to
        const usable = isAdmin
          ? data.items
          : data.items.filter((a) => a.access_status === "approved");
        setAgents(usable);
        if (usable.length > 0 && !selectedAgentId) {
          setSelectedAgentId(usable[0].id);
        }
      })
      .catch(() => {})
      .finally(() => setAgentsLoading(false));
  }, [isAdmin]);

  // ── Step 4: Schedule ────────────────────────────────────────────────────────
  const [schedule, setSchedule] = useState({
    start: "10:00", end: "19:00",
    days: { Mon: true, Tue: true, Wed: true, Thu: true, Fri: true, Sat: false, Sun: false },
    timezone: "Asia/Kolkata",
    cpm: 1,
    retries: 1,
  });

  function next() {
    if (step === 1 && !basics.name.trim())   { toast.error("Campaign name is required"); return; }
    if (step === 2 && !contactFile)           { toast.error("Please upload a contacts file"); return; }
    if (step === 3 && !selectedAgentId)       { toast.error("Please select an agent"); return; }
    if (step < 4) setStep(step + 1);
  }
  function back() { if (step > 1) setStep(step - 1); }

  async function submit(launch: boolean) {
    if (submitting) return;
    if (!selectedAgentId) { toast.error("Please select an agent"); return; }
    setSubmitting(true);
    try {
      // 1. Create campaign — use existing agent, no new agent creation
      const callingDays = (Object.keys(schedule.days) as (keyof typeof schedule.days)[])
        .filter((d) => schedule.days[d])
        .map((d) => DAY_CODE[d]);

      const { data: campaignData } = await campaignsApi.create({
        name:                  basics.name,
        description:           basics.description || undefined,
        goal:                  GOAL_MAP[basics.goal] ?? "lead_generation",
        agent_template_id:     selectedAgentId,          // ← reuse existing agent
        calling_window_start:  schedule.start + ":00",
        calling_window_end:    schedule.end   + ":00",
        calling_days:          callingDays,
        timezone:              schedule.timezone,
        calls_per_minute:      schedule.cpm,
        max_retries:           schedule.retries,
      });

      // 2. Upload contacts
      if (contactFile) {
        const { data: uploadData } = await campaignsApi.uploadContacts(campaignData.id, contactFile);
        toast.success(`Uploaded ${uploadData.count} contacts`);
      }

      // 3. Launch or save as draft
      if (launch) {
        await campaignsApi.launch(campaignData.id);
        toast.success("Campaign launched! AI is starting calls.");
        navigate({ to: "/dashboard" });
      } else {
        toast.success("Campaign saved as draft");
        navigate({ to: "/campaigns" });
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail ?? e?.message ?? "Something went wrong";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  }

  const selectedAgent = agents.find((a) => a.id === selectedAgentId);

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Create New Campaign</h1>
          <p className="text-sm text-muted-foreground mt-1">Set up an AI calling campaign in 4 steps</p>
        </div>
        <Button variant="ghost" onClick={() => navigate({ to: "/campaigns" })}>
          <X className="h-4 w-4" /> Cancel
        </Button>
      </div>

      {/* Stepper */}
      <div className="rounded-xl bg-card border border-border p-5">
        <div className="flex items-center">
          {stepsList.map((s, i) => (
            <div key={s.n} className="flex items-center flex-1 last:flex-initial">
              <div className="flex items-center gap-3">
                <div className={`h-9 w-9 rounded-full grid place-items-center text-sm font-semibold border-2 transition-all ${
                  step > s.n  ? "bg-success border-success text-white" :
                  step === s.n ? "bg-gradient-primary border-transparent text-white shadow-glow" :
                                 "border-border text-muted-foreground"
                }`}>
                  {step > s.n ? <Check className="h-4 w-4" /> : s.n}
                </div>
                <div className="hidden sm:block">
                  <div className={`text-sm font-medium ${step >= s.n ? "" : "text-muted-foreground"}`}>{s.title}</div>
                  <div className="text-xs text-muted-foreground">{s.desc}</div>
                </div>
              </div>
              {i < stepsList.length - 1 && (
                <div className={`flex-1 h-px mx-4 ${step > s.n ? "bg-success" : "bg-border"}`} />
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl bg-card border border-border p-6 space-y-6 fade-up" key={step}>

        {/* ── Step 1: Basics ──────────────────────────────────────────────── */}
        {step === 1 && (
          <>
            <div>
              <h2 className="text-lg font-semibold">Campaign Basics</h2>
              <p className="text-sm text-muted-foreground">Tell us what this campaign is about</p>
            </div>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label>Campaign Name *</Label>
                <Input
                  value={basics.name}
                  onChange={(e) => setBasics({ ...basics, name: e.target.value })}
                  placeholder="e.g. Butterfly Valve Q4 Outreach"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Description</Label>
                <Textarea
                  value={basics.description}
                  onChange={(e) => setBasics({ ...basics, description: e.target.value })}
                  placeholder="Brief description of campaign goals…"
                  rows={3}
                />
              </div>
              <div className="space-y-2">
                <Label>Campaign Goal</Label>
                <RadioGroup
                  value={basics.goal}
                  onValueChange={(v) => setBasics({ ...basics, goal: v })}
                  className="grid grid-cols-2 gap-3"
                >
                  {["Lead Generation", "Product Demo", "Follow-up", "Cold Outreach"].map((g) => (
                    <label key={g} className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                      basics.goal === g ? "border-primary bg-primary/10" : "border-border hover:border-primary/40"
                    }`}>
                      <RadioGroupItem value={g} />
                      <span className="text-sm">{g}</span>
                    </label>
                  ))}
                </RadioGroup>
              </div>
            </div>
          </>
        )}

        {/* ── Step 2: Contacts ────────────────────────────────────────────── */}
        {step === 2 && (
          <>
            <div>
              <h2 className="text-lg font-semibold">Upload Contacts</h2>
              <p className="text-sm text-muted-foreground">
                CSV or Excel file — must have a{" "}
                <code className="text-xs bg-surface-2 px-1 py-0.5 rounded">phone</code> column.
                Optional: name, company, email.
              </p>
            </div>
            <DropZone
              file={fileInfo}
              onFile={(info, raw) => { setFileInfo(info); setContactFile(raw); }}
            />
            {fileInfo && <ContactPreview />}
            <div className="text-sm text-muted-foreground">
              Required column:{" "}
              <code className="bg-surface-2 px-1 py-0.5 rounded text-xs">phone</code>
              {" "}· Optional:{" "}
              <code className="bg-surface-2 px-1 py-0.5 rounded text-xs">name</code>,{" "}
              <code className="bg-surface-2 px-1 py-0.5 rounded text-xs">company</code>,{" "}
              <code className="bg-surface-2 px-1 py-0.5 rounded text-xs">email</code>
            </div>
          </>
        )}

        {/* ── Step 3: Select Agent ─────────────────────────────────────────── */}
        {step === 3 && (
          <>
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold">Select AI Agent</h2>
                <p className="text-sm text-muted-foreground">
                  Choose an existing agent to use for this campaign
                </p>
              </div>
              <Link to="/agents">
                <Button variant="outline" size="sm">
                  <Plus className="h-3 w-3" /> Create New Agent
                </Button>
              </Link>
            </div>

            {agentsLoading ? (
              <div className="flex items-center justify-center h-40 text-muted-foreground">
                <Loader2 className="h-6 w-6 animate-spin mr-2" /> Loading agents…
              </div>
            ) : agents.length === 0 ? (
              /* ── No agents yet ─────────────────────────────────────────── */
              <div className="flex flex-col items-center justify-center h-60 gap-4 rounded-xl border-2 border-dashed border-border text-muted-foreground">
                <Bot className="h-12 w-12 opacity-30" />
                <div className="text-center">
                  <p className="text-sm font-medium">No agents created yet</p>
                  <p className="text-xs mt-1">
                    Go to the AI Agents section to create your first agent, then come back here.
                  </p>
                </div>
                <Link to="/agents">
                  <Button className="bg-gradient-primary text-white shadow-glow">
                    <Plus className="h-4 w-4" /> Create Agent
                  </Button>
                </Link>
              </div>
            ) : (
              /* ── Agent selection grid ──────────────────────────────────── */
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                {agents.map((a) => {
                  const voice     = voices.find((v) => v.id === a.voice_id) ?? voices[0];
                  const isSelected = a.id === selectedAgentId;
                  return (
                    <button
                      key={a.id}
                      type="button"
                      onClick={() => setSelectedAgentId(a.id)}
                      className={`text-left rounded-xl border-2 p-5 transition-all flex flex-col ${
                        isSelected
                          ? "border-primary bg-primary/5 shadow-glow"
                          : "border-border hover:border-primary/40 bg-card"
                      }`}
                    >
                      {/* Card header */}
                      <div className="flex items-start justify-between mb-3">
                        <div className={`h-12 w-12 rounded-lg grid place-items-center flex-shrink-0 ${
                          isSelected ? "bg-gradient-primary text-white" : "bg-surface-2 text-muted-foreground"
                        }`}>
                          <Bot className="h-6 w-6" />
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs px-2 py-0.5 rounded bg-surface-3 text-muted-foreground">
                            {a.language}
                          </span>
                          {isSelected && (
                            <span className="h-5 w-5 rounded-full bg-primary grid place-items-center">
                              <Check className="h-3 w-3 text-white" />
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Agent name */}
                      <h3 className={`font-semibold ${isSelected ? "text-primary" : ""}`}>{a.name}</h3>
                      {a.description && (
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{a.description}</p>
                      )}

                      {/* Details */}
                      <div className="mt-3 text-xs text-muted-foreground space-y-1 flex-1">
                        <div>Voice: <span className="text-foreground">{voice.name}</span></div>
                        <div>Model: <span className="text-foreground">{a.llm_model.split("/").pop()}</span></div>
                        <div>
                          Welcome:{" "}
                          <span className="text-foreground line-clamp-1">
                            {a.welcome_message || <em>not set</em>}
                          </span>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}

            {/* Selected agent summary */}
            {selectedAgent && (
              <div className="rounded-lg border border-primary/30 bg-primary/5 p-4 flex items-center gap-3">
                <div className="h-9 w-9 rounded-lg bg-gradient-primary grid place-items-center text-white flex-shrink-0">
                  <Bot className="h-5 w-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm">
                    Selected: <span className="text-primary">{selectedAgent.name}</span>
                  </div>
                  <div className="text-xs text-muted-foreground truncate">
                    {selectedAgent.language} · {selectedAgent.llm_model.split("/").pop()} · voice: {voices.find(v => v.id === selectedAgent.voice_id)?.name ?? selectedAgent.voice_id}
                  </div>
                </div>
                <Check className="h-4 w-4 text-primary flex-shrink-0" />
              </div>
            )}
          </>
        )}

        {/* ── Step 4: Schedule & Launch ────────────────────────────────────── */}
        {step === 4 && (
          <>
            <div>
              <h2 className="text-lg font-semibold">Schedule & Launch</h2>
              <p className="text-sm text-muted-foreground">When should we make these calls?</p>
            </div>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label>Start Time</Label>
                  <Input
                    type="time"
                    value={schedule.start}
                    onChange={(e) => setSchedule({ ...schedule, start: e.target.value })}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>End Time</Label>
                  <Input
                    type="time"
                    value={schedule.end}
                    onChange={(e) => setSchedule({ ...schedule, end: e.target.value })}
                  />
                </div>
              </div>
              <div>
                <Label className="mb-2 block">Days of the Week</Label>
                <div className="flex flex-wrap gap-2">
                  {(Object.keys(schedule.days) as (keyof typeof schedule.days)[]).map((d) => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => setSchedule({ ...schedule, days: { ...schedule.days, [d]: !schedule.days[d] } })}
                      className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                        schedule.days[d]
                          ? "bg-gradient-primary text-white"
                          : "bg-surface-2 text-muted-foreground border border-border hover:text-foreground"
                      }`}
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Time Zone</Label>
                <Select
                  value={schedule.timezone}
                  onValueChange={(v) => setSchedule({ ...schedule, timezone: v })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "America/New_York"].map((x) => (
                      <SelectItem key={x} value={x}>{x}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <Label className="text-xs">Calls per minute: {schedule.cpm}</Label>
                  <Slider
                    value={[schedule.cpm]}
                    onValueChange={([v]) => setSchedule({ ...schedule, cpm: v })}
                    min={1} max={10} step={1}
                    className="mt-2"
                  />
                </div>
                <div>
                  <Label className="text-xs">Max retries on no-answer: {schedule.retries}</Label>
                  <Slider
                    value={[schedule.retries]}
                    onValueChange={([v]) => setSchedule({ ...schedule, retries: v })}
                    min={0} max={3} step={1}
                    className="mt-2"
                  />
                </div>
              </div>

              {/* Review box */}
              <div className="rounded-lg bg-surface-2 border border-border p-4">
                <div className="font-medium text-sm mb-2">Review</div>
                <div className="text-xs text-muted-foreground space-y-1">
                  <div>
                    Campaign:{" "}
                    <span className="text-foreground font-medium">{basics.name}</span>
                  </div>
                  <div>
                    Contacts:{" "}
                    <span className="text-foreground font-medium">
                      {fileInfo ? `${fileInfo.rows} rows · ${fileInfo.name}` : "—"}
                    </span>
                  </div>
                  <div>
                    Agent:{" "}
                    <span className="text-foreground font-medium">
                      {selectedAgent ? `${selectedAgent.name} · ${selectedAgent.language}` : "—"}
                    </span>
                  </div>
                  <div>
                    Window:{" "}
                    <span className="text-foreground font-medium">
                      {schedule.start}–{schedule.end} {schedule.timezone}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Wizard nav */}
      <div className="flex items-center justify-between">
        <Button variant="outline" onClick={back} disabled={step === 1 || submitting}>
          <ChevronLeft className="h-4 w-4" /> Back
        </Button>
        <div className="flex gap-2">
          {step === 4 ? (
            <>
              <Button variant="outline" onClick={() => submit(false)} disabled={submitting}>
                <Save className="h-4 w-4" /> {submitting ? "Saving…" : "Save as Draft"}
              </Button>
              <Button
                onClick={() => submit(true)}
                disabled={submitting}
                className="bg-gradient-primary text-white shadow-glow"
              >
                <Rocket className="h-4 w-4" /> {submitting ? "Launching…" : "Launch Campaign"}
              </Button>
            </>
          ) : (
            <Button
              onClick={next}
              disabled={step === 3 && agents.length === 0}
              className="bg-gradient-primary text-white shadow-glow"
            >
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── DropZone ──────────────────────────────────────────────────────────────────
function DropZone({
  file,
  onFile,
}: {
  file: { name: string; size: number; rows: number } | null;
  onFile: (info: { name: string; size: number; rows: number }, raw: File) => void;
}) {
  const [drag, setDrag] = useState(false);

  function pick(f: File) {
    onFile({ name: f.name, size: f.size, rows: Math.max(Math.floor(f.size / 80), 1) }, f);
    toast.success(`${f.name} ready to upload`);
  }

  if (file) {
    return (
      <div className="rounded-xl border border-border bg-surface-2/50 p-5 flex items-center gap-4">
        <div className="h-12 w-12 rounded-lg bg-success/15 grid place-items-center text-success">
          <FileSpreadsheet className="h-6 w-6" />
        </div>
        <div className="flex-1">
          <div className="font-medium text-sm">{file.name}</div>
          <div className="text-xs text-muted-foreground">
            {(file.size / 1024).toFixed(1)} KB · ~{file.rows} rows
          </div>
        </div>
        <span className="text-xs px-2 py-1 rounded bg-success/15 text-success">Ready</span>
      </div>
    );
  }

  return (
    <label
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        const f = e.dataTransfer.files[0];
        if (f) pick(f);
      }}
      className={`block rounded-xl border-2 border-dashed cursor-pointer p-12 text-center transition-all ${
        drag ? "border-primary bg-primary/5 shadow-glow" : "border-border hover:border-primary/40"
      }`}
    >
      <input
        type="file"
        accept=".csv,.xlsx,.xls"
        className="hidden"
        onChange={(e) => e.target.files?.[0] && pick(e.target.files[0])}
      />
      <Upload className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
      <div className="font-medium">Drop CSV or Excel here, or click to browse</div>
      <div className="text-xs text-muted-foreground mt-2">
        Required: <code className="bg-surface-3 px-1 rounded">phone</code> column · Optional: name, company, email · max 10MB
      </div>
    </label>
  );
}

// ── ContactPreview ────────────────────────────────────────────────────────────
function ContactPreview() {
  const sample = [
    { name: "Rajesh Sharma",  phone: "+91 98765 43210", company: "Baba Valves",      email: "rajesh@baba.com"  },
    { name: "Priya Iyer",     phone: "+91 99887 11223", company: "Aqua Flow",         email: "priya@aqua.in"    },
    { name: "Amit Patel",     phone: "+91 90909 88776", company: "Petro Industries",  email: "amit@petro.co"    },
  ];
  return (
    <div className="rounded-xl border border-border bg-surface-2/40 overflow-hidden">
      <div className="px-4 py-3 border-b border-border text-xs text-muted-foreground">
        Expected column format (sample)
      </div>
      <table className="w-full text-sm">
        <thead className="bg-surface-3/40 text-xs">
          <tr>
            {["name", "phone", "company", "email"].map((h) => (
              <th key={h} className="px-4 py-2 text-left font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sample.map((r, i) => (
            <tr key={i} className="border-t border-border/60">
              <td className="px-4 py-2">{r.name}</td>
              <td className="px-4 py-2 font-mono text-xs">{r.phone}</td>
              <td className="px-4 py-2">{r.company}</td>
              <td className="px-4 py-2 text-muted-foreground">{r.email}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
