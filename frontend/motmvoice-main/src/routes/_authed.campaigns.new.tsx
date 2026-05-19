import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useRef, useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Slider } from "@/components/ui/slider";
import { Check, Upload, FileSpreadsheet, Sparkles, Play, ChevronLeft, ChevronRight, Rocket, Save, X, ChevronDown } from "lucide-react";
import { voices, promptTemplates } from "@/lib/mock-data";
import { agentsApi, campaignsApi } from "@/lib/api";
import { toast } from "sonner";

export const Route = createFileRoute("/_authed/campaigns/new")({
  head: () => ({ meta: [{ title: "New Campaign — MOTMVoice" }] }),
  component: NewCampaign,
});

const stepsList = [
  { n: 1, title: "Basics", desc: "Name & goal" },
  { n: 2, title: "Contacts", desc: "Upload CSV" },
  { n: 3, title: "AI Agent", desc: "Voice & prompt" },
  { n: 4, title: "Schedule", desc: "Launch" },
];

// Map frontend display goals → backend enum values
const GOAL_MAP: Record<string, string> = {
  "Lead Generation": "lead_generation",
  "Product Demo": "announcement",
  "Follow-up": "follow_up",
  "Cold Outreach": "lead_generation",
};

// Map frontend display days → backend short codes
const DAY_CODE: Record<string, string> = {
  Mon: "mon", Tue: "tue", Wed: "wed", Thu: "thu", Fri: "fri", Sat: "sat", Sun: "sun",
};

function NewCampaign() {
  const [step, setStep] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  const [basics, setBasics] = useState({ name: "", description: "", goal: "Lead Generation" });
  const [contactFile, setContactFile] = useState<File | null>(null);
  const [fileInfo, setFileInfo] = useState<{ name: string; size: number; rows: number } | null>(null);
  const [agent, setAgent] = useState({
    name: "Sales Agent",
    voiceId: "C8R8ahkE5XosZ8qPpSPy",
    language: "Hinglish",
    welcome: "",
    prompt: "",
    maxDuration: 10,
    model: "llama-3.3-70b-versatile",
    temperature: 0.7,
  });

  // Pre-fill agent fields from the most recently created agent template
  useEffect(() => {
    agentsApi.list().then(({ data }) => {
      if (data.items.length > 0) {
        const last = data.items[0];
        setAgent(prev => ({
          ...prev,
          name:        last.name              || prev.name,
          voiceId:     last.voice_id          || prev.voiceId,
          language:    last.language          || prev.language,
          welcome:     last.welcome_message   ?? prev.welcome,
          prompt:      last.system_prompt     ?? prev.prompt,
          maxDuration: last.max_call_duration_seconds
                         ? Math.round(last.max_call_duration_seconds / 60)
                         : prev.maxDuration,
          model:       last.llm_model         || prev.model,
          temperature: last.llm_temperature   ?? prev.temperature,
        }));
      }
    }).catch(() => {});
  }, []);
  const [advanced, setAdvanced] = useState(false);
  const [schedule, setSchedule] = useState({
    start: "10:00", end: "19:00",
    days: { Mon: true, Tue: true, Wed: true, Thu: true, Fri: true, Sat: false, Sun: false },
    timezone: "Asia/Kolkata",
    cpm: 1,
    retries: 1,
  });

  function next() {
    if (step === 1 && !basics.name.trim()) { toast.error("Campaign name is required"); return; }
    if (step === 2 && !contactFile) { toast.error("Please upload a contacts file"); return; }
    if (step < 4) setStep(step + 1);
  }
  function back() { if (step > 1) setStep(step - 1); }

  async function submit(launch: boolean) {
    if (submitting) return;
    setSubmitting(true);
    try {
      // 1. Create agent template
      const { data: agentData } = await agentsApi.create({
        name: agent.name,
        language: agent.language,
        welcome_message: agent.welcome,
        system_prompt: agent.prompt,
        voice_id: agent.voiceId,
        voice_provider: "elevenlabs",
        llm_model: agent.model,
        llm_temperature: agent.temperature,
        max_call_duration_seconds: agent.maxDuration * 60,
      });

      // 2. Create campaign
      const callingDays = (Object.keys(schedule.days) as (keyof typeof schedule.days)[])
        .filter((d) => schedule.days[d])
        .map((d) => DAY_CODE[d]);

      const { data: campaignData } = await campaignsApi.create({
        name: basics.name,
        description: basics.description || undefined,
        goal: GOAL_MAP[basics.goal] ?? "lead_generation",
        agent_template_id: agentData.id,
        calling_window_start: schedule.start + ":00",
        calling_window_end: schedule.end + ":00",
        calling_days: callingDays,
        timezone: schedule.timezone,
        calls_per_minute: schedule.cpm,
        max_retries: schedule.retries,
      });

      // 3. Upload contacts
      if (contactFile) {
        const { data: uploadData } = await campaignsApi.uploadContacts(campaignData.id, contactFile);
        toast.success(`Uploaded ${uploadData.count} contacts`);
      }

      // 4. Launch or save as draft
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

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Create New Campaign</h1>
          <p className="text-sm text-muted-foreground mt-1">Set up an AI calling campaign in 4 steps</p>
        </div>
        <Button variant="ghost" onClick={() => navigate({ to: "/campaigns" })}><X className="h-4 w-4" /> Cancel</Button>
      </div>

      {/* Stepper */}
      <div className="rounded-xl bg-card border border-border p-5">
        <div className="flex items-center">
          {stepsList.map((s, i) => (
            <div key={s.n} className="flex items-center flex-1 last:flex-initial">
              <div className="flex items-center gap-3">
                <div className={`h-9 w-9 rounded-full grid place-items-center text-sm font-semibold border-2 transition-all ${
                  step > s.n ? "bg-success border-success text-white" :
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
              {i < stepsList.length - 1 && <div className={`flex-1 h-px mx-4 ${step > s.n ? "bg-success" : "bg-border"}`} />}
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl bg-card border border-border p-6 space-y-6 fade-up" key={step}>
        {step === 1 && (
          <>
            <div>
              <h2 className="text-lg font-semibold">Campaign Basics</h2>
              <p className="text-sm text-muted-foreground">Tell us what this campaign is about</p>
            </div>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label>Campaign Name *</Label>
                <Input value={basics.name} onChange={(e) => setBasics({ ...basics, name: e.target.value })} placeholder="e.g. Butterfly Valve Q4 Outreach" />
              </div>
              <div className="space-y-1.5">
                <Label>Description</Label>
                <Textarea value={basics.description} onChange={(e) => setBasics({ ...basics, description: e.target.value })} placeholder="Brief description of campaign goals…" rows={3} />
              </div>
              <div className="space-y-2">
                <Label>Campaign Goal</Label>
                <RadioGroup value={basics.goal} onValueChange={(v) => setBasics({ ...basics, goal: v })} className="grid grid-cols-2 gap-3">
                  {["Lead Generation", "Product Demo", "Follow-up", "Cold Outreach"].map(g => (
                    <label key={g} className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${basics.goal === g ? "border-primary bg-primary/10" : "border-border hover:border-primary/40"}`}>
                      <RadioGroupItem value={g} />
                      <span className="text-sm">{g}</span>
                    </label>
                  ))}
                </RadioGroup>
              </div>
            </div>
          </>
        )}

        {step === 2 && (
          <>
            <div>
              <h2 className="text-lg font-semibold">Upload Contacts</h2>
              <p className="text-sm text-muted-foreground">CSV or Excel file — must have a <code className="text-xs bg-surface-2 px-1 py-0.5 rounded">phone</code> column. Optional: name, company, email.</p>
            </div>
            <DropZone file={fileInfo} onFile={(info, raw) => { setFileInfo(info); setContactFile(raw); }} />
            {fileInfo && <ContactPreview rows={fileInfo.rows} />}
            <div className="text-sm text-muted-foreground">
              Required column: <code className="bg-surface-2 px-1 py-0.5 rounded text-xs">phone</code> · Optional: <code className="bg-surface-2 px-1 py-0.5 rounded text-xs">name</code>, <code className="bg-surface-2 px-1 py-0.5 rounded text-xs">company</code>, <code className="bg-surface-2 px-1 py-0.5 rounded text-xs">email</code>
            </div>
          </>
        )}

        {step === 3 && (
          <>
            <div>
              <h2 className="text-lg font-semibold">Configure AI Agent</h2>
              <p className="text-sm text-muted-foreground">Choose voice, language and write the system prompt</p>
            </div>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label>Agent Name</Label>
                <Input value={agent.name} onChange={(e) => setAgent({ ...agent, name: e.target.value })} />
              </div>
              <div>
                <Label className="mb-2 block">Voice Selection</Label>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {voices.map((v) => (
                    <button key={v.id} type="button" onClick={() => setAgent({ ...agent, voiceId: v.id })}
                      className={`text-left p-3 rounded-lg border transition-all ${agent.voiceId === v.id ? "border-primary bg-primary/10 shadow-glow" : "border-border hover:border-primary/40"}`}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="font-semibold text-sm">{v.name}</div>
                        <span className="h-7 w-7 rounded-full bg-primary/15 grid place-items-center text-primary"><Play className="h-3 w-3" /></span>
                      </div>
                      <div className="text-xs text-muted-foreground">{v.desc}</div>
                      <div className="mt-2 flex gap-1.5">
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-3 text-muted-foreground">{v.lang}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-3 text-muted-foreground">{v.gender === "F" ? "Female" : "Male"}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label>Language</Label>
                  <Select value={agent.language} onValueChange={(v) => setAgent({ ...agent, language: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {["Hinglish", "Hindi", "English", "Marathi", "Tamil", "Telugu", "Bengali", "Gujarati"].map(x => <SelectItem key={x} value={x}>{x}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Use Template</Label>
                  <Select onValueChange={(id) => {
                    const t = promptTemplates.find(p => p.id === id);
                    if (t) toast.success(`Loaded ${t.name} template`);
                  }}>
                    <SelectTrigger><SelectValue placeholder="Choose a template…" /></SelectTrigger>
                    <SelectContent>
                      {promptTemplates.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Welcome Message</Label>
                <Textarea value={agent.welcome} onChange={(e) => setAgent({ ...agent, welcome: e.target.value })} rows={2} />
              </div>
              <div className="grid lg:grid-cols-3 gap-4">
                <div className="lg:col-span-2 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label>System Prompt</Label>
                    <Button type="button" size="sm" variant="outline" onClick={() => toast.success("Prompt enhanced with AI ✨")}>
                      <Sparkles className="h-3 w-3" /> AI Improve
                    </Button>
                  </div>
                  <Textarea value={agent.prompt} onChange={(e) => setAgent({ ...agent, prompt: e.target.value })}
                    className="font-mono text-xs min-h-[300px] resize-y" />
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>{agent.prompt.length} chars · ~{Math.ceil(agent.prompt.length / 4)} tokens</span>
                  </div>
                </div>
                <div className="rounded-lg bg-surface-2 border border-border p-4 space-y-3 text-xs">
                  <div className="font-semibold text-sm">💡 Best Practices</div>
                  <ul className="space-y-2 text-muted-foreground">
                    <li>• Keep responses to 1-2 sentences</li>
                    <li>• Define a clear goal upfront</li>
                    <li>• Specify the language/tone explicitly</li>
                    <li>• Add example exchanges</li>
                    <li>• Define when to end the call</li>
                  </ul>
                </div>
              </div>
              <button onClick={() => setAdvanced(!advanced)} className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
                <ChevronDown className={`h-4 w-4 transition-transform ${advanced ? "rotate-180" : ""}`} />
                Advanced Settings
              </button>
              {advanced && (
                <div className="rounded-lg bg-surface-2 border border-border p-4 space-y-4">
                  <div>
                    <Label className="text-xs">Max Call Duration: {agent.maxDuration} min</Label>
                    <Slider value={[agent.maxDuration]} onValueChange={([v]) => setAgent({ ...agent, maxDuration: v })} min={1} max={15} step={1} className="mt-2" />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label className="text-xs">LLM Model</Label>
                      <Select value={agent.model} onValueChange={(v) => setAgent({ ...agent, model: v })}>
                        <SelectTrigger className="mt-2"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama-3.1-70b-versatile"].map(x => <SelectItem key={x} value={x}>{x}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="text-xs">Temperature: {agent.temperature.toFixed(1)}</Label>
                      <Slider value={[agent.temperature * 10]} onValueChange={([v]) => setAgent({ ...agent, temperature: v / 10 })} min={0} max={10} step={1} className="mt-2" />
                    </div>
                  </div>
                </div>
              )}
            </div>
          </>
        )}

        {step === 4 && (
          <>
            <div>
              <h2 className="text-lg font-semibold">Schedule & Launch</h2>
              <p className="text-sm text-muted-foreground">When should we make these calls?</p>
            </div>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5"><Label>Start Time</Label><Input type="time" value={schedule.start} onChange={(e) => setSchedule({ ...schedule, start: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>End Time</Label><Input type="time" value={schedule.end} onChange={(e) => setSchedule({ ...schedule, end: e.target.value })} /></div>
              </div>
              <div>
                <Label className="mb-2 block">Days of the Week</Label>
                <div className="flex flex-wrap gap-2">
                  {(Object.keys(schedule.days) as (keyof typeof schedule.days)[]).map((d) => (
                    <button key={d} type="button"
                      onClick={() => setSchedule({ ...schedule, days: { ...schedule.days, [d]: !schedule.days[d] } })}
                      className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${schedule.days[d] ? "bg-gradient-primary text-white" : "bg-surface-2 text-muted-foreground border border-border hover:text-foreground"}`}>
                      {d}
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Time Zone</Label>
                <Select value={schedule.timezone} onValueChange={(v) => setSchedule({ ...schedule, timezone: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "America/New_York"].map(x => <SelectItem key={x} value={x}>{x}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <Label className="text-xs">Calls per minute: {schedule.cpm}</Label>
                  <Slider value={[schedule.cpm]} onValueChange={([v]) => setSchedule({ ...schedule, cpm: v })} min={1} max={10} step={1} className="mt-2" />
                </div>
                <div>
                  <Label className="text-xs">Max retries on no-answer: {schedule.retries}</Label>
                  <Slider value={[schedule.retries]} onValueChange={([v]) => setSchedule({ ...schedule, retries: v })} min={0} max={3} step={1} className="mt-2" />
                </div>
              </div>
              <div className="rounded-lg bg-surface-2 border border-border p-4">
                <div className="font-medium text-sm mb-1">Review</div>
                <div className="text-xs text-muted-foreground space-y-1">
                  <div>Campaign: <span className="text-foreground font-medium">{basics.name}</span></div>
                  <div>Contacts: <span className="text-foreground font-medium">{fileInfo ? `${fileInfo.rows} rows · ${fileInfo.name}` : "—"}</span></div>
                  <div>Agent: <span className="text-foreground font-medium">{agent.name} · {agent.language}</span></div>
                  <div>Window: <span className="text-foreground font-medium">{schedule.start}–{schedule.end} {schedule.timezone}</span></div>
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
              <Button onClick={() => submit(true)} disabled={submitting} className="bg-gradient-primary text-white shadow-glow">
                <Rocket className="h-4 w-4" /> {submitting ? "Launching…" : "Launch Campaign"}
              </Button>
            </>
          ) : (
            <Button onClick={next} className="bg-gradient-primary text-white shadow-glow">
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function DropZone({ file, onFile }: {
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
          <div className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(1)} KB · ~{file.rows} rows</div>
        </div>
        <span className="text-xs px-2 py-1 rounded bg-success/15 text-success">Ready</span>
      </div>
    );
  }

  return (
    <label
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) pick(f); }}
      className={`block rounded-xl border-2 border-dashed cursor-pointer p-12 text-center transition-all ${drag ? "border-primary bg-primary/5 shadow-glow" : "border-border hover:border-primary/40"}`}
    >
      <input type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={(e) => e.target.files?.[0] && pick(e.target.files[0])} />
      <Upload className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
      <div className="font-medium">Drop CSV or Excel here, or click to browse</div>
      <div className="text-xs text-muted-foreground mt-2">Required: <code className="bg-surface-3 px-1 rounded">phone</code> column · Optional: name, company, email · max 10MB</div>
    </label>
  );
}

function ContactPreview({ rows }: { rows: number }) {
  const sample = [
    { name: "Rajesh Sharma", phone: "+91 98765 43210", company: "Baba Valves", email: "rajesh@baba.com" },
    { name: "Priya Iyer", phone: "+91 99887 11223", company: "Aqua Flow", email: "priya@aqua.in" },
    { name: "Amit Patel", phone: "+91 90909 88776", company: "Petro Industries", email: "amit@petro.co" },
  ];
  return (
    <div className="rounded-xl border border-border bg-surface-2/40 overflow-hidden">
      <div className="px-4 py-3 border-b border-border text-xs text-muted-foreground">Expected column format (sample)</div>
      <table className="w-full text-sm">
        <thead className="bg-surface-3/40 text-xs">
          <tr>{["name", "phone", "company", "email"].map(h => <th key={h} className="px-4 py-2 text-left font-medium">{h}</th>)}</tr>
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
