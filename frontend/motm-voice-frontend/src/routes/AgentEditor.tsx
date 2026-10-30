import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft,
  Braces,
  CalendarDays,
  Check,
  Download,
  FileText,
  Loader2,
  Paperclip,
  Pencil,
  Phone,
  Save,
  Settings2,
  Sparkles,
  Trash2,
  Undo2,
  Upload,
  Wrench,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Slider } from "@/components/ui/slider";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { LanguageSelect, VoiceSelect } from "@/components/shared/VoiceFields";
import { useAuth } from "@/lib/auth";
import { useAgent, useAgentCalendar, useCreateAgent, useCustomizeAgent, useLeadsMeta, useUpdateAgent } from "@/lib/hooks";
import { agentsApi, apiErrorMessage } from "@/lib/api";
import {
  AGENT_TOOLS,
  DEFAULT_GREETING,
  DEFAULT_INSTRUCTIONS,
  SYSTEM_VARIABLES,
  findVariables,
} from "@/lib/agentTemplate";
import { cn } from "@/lib/utils";
import type { AgentCreate, AgentTemplate, CalendarSettings } from "@/lib/types";
import { TestCallDialog } from "./Agents";

type Tab = "instructions" | "variables" | "tools" | "brochure" | "calendar" | "settings";

const TABS: { key: Tab; label: string; icon: typeof FileText }[] = [
  { key: "instructions", label: "Instructions", icon: FileText },
  { key: "variables", label: "Variables", icon: Braces },
  { key: "tools", label: "Tools", icon: Wrench },
  { key: "brochure", label: "Brochure", icon: Paperclip },
  { key: "calendar", label: "Calendar", icon: CalendarDays },
  { key: "settings", label: "Settings", icon: Settings2 },
];

const TOOL_HELP: Record<string, string> = {
  end_interaction: "Ends the call once the conversation is over. If the agent hasn't said goodbye yet, it says one first.",
  book_next_step:
    "Books the demo, meeting or follow-up the prospect agreed to and returns a reference. With a Google Calendar connected (Calendar tab) it creates a real event with a Meet link and invites the customer; otherwise it notes the agreed time. Shows on the call and the lead.",
  check_calendar:
    "Looks up free times in the connected Google Calendar so the agent only offers slots that are really open. Only on calls where this agent has a calendar connected (Calendar tab).",
  switch_language: "Switches the spoken language mid-call when the caller asks for one of your enabled languages.",
  send_brochure:
    "When the customer agrees to receive the brochure, it is emailed to them right after the call. Only on calls where this agent has a brochure (Brochure tab) and your mailbox is connected.",
  transfer_call:
    "When the customer asks for a person, or your instructions say to transfer, the agent asks them to hold and rings your transfer number. Once someone answers, the customer is connected to them and the agent goes quiet. If nobody answers within 30 seconds, the agent promises a callback and carries on. Only when a transfer number is set (Settings tab).",
};

const NEW_AGENT: Required<AgentCreate> = {
  name: "New agent",
  description: "",
  language: "hinglish",
  welcome_message: DEFAULT_GREETING,
  system_prompt: DEFAULT_INSTRUCTIONS,
  variables: {},
  voice_id: "",
  llm_temperature: 0.7,
  speech_pace: 1,
  max_call_duration_seconds: 600,
  transfer_number: "",
};

interface ChatTurn {
  request: string;
  summary?: string;
  error?: string;
  undo?: { greeting: string; instructions: string };
}

export default function AgentEditor() {
  const { id } = useParams<{ id: string }>();
  const isNew = !id || id === "new";
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const agent = useAgent(isNew ? undefined : id);
  const createAgent = useCreateAgent();
  const updateAgent = useUpdateAgent();

  const [form, setForm] = useState<Required<AgentCreate>>(NEW_AGENT);
  const [saved, setSaved] = useState<Required<AgentCreate>>(NEW_AGENT);
  const [tab, setTab] = useState<Tab>("instructions");
  const [testCallOpen, setTestCallOpen] = useState(false);

  useEffect(() => {
    if (!agent.data) return;
    const a = agent.data;
    const loaded = {
      name: a.name, description: a.description ?? "", language: a.language,
      welcome_message: a.welcome_message, system_prompt: a.system_prompt, variables: a.variables ?? {},
      voice_id: a.voice_id ?? "", llm_temperature: a.llm_temperature, speech_pace: a.speech_pace, max_call_duration_seconds: a.max_call_duration_seconds,
      transfer_number: a.transfer_number ?? "",
    };
    setForm(loaded);
    setSaved(loaded);
  }, [agent.data]);

  const update = <K extends keyof AgentCreate>(key: K, value: Required<AgentCreate>[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const variables = useMemo(
    () => findVariables(form.welcome_message, form.system_prompt).filter((v) => !SYSTEM_VARIABLES.includes(v)),
    [form.welcome_message, form.system_prompt]
  );
  const dirty = JSON.stringify(form) !== JSON.stringify(saved);
  const canEdit = isNew ? isAdmin : isAdmin || !!agent.data?.can_edit;
  const saving = createAgent.isPending || updateAgent.isPending;

  async function handleSave() {
    if (!form.name.trim()) {
      toast.error("Give the agent a name");
      return;
    }
    // Only keep defaults for placeholders still in the script
    const data = { ...form, variables: Object.fromEntries(variables.map((v) => [v, form.variables[v] ?? ""])) };
    try {
      if (isNew) {
        const created = await createAgent.mutateAsync(data);
        toast.success("Agent created");
        navigate(`/agents/${created.data.id}`, { replace: true });
      } else {
        await updateAgent.mutateAsync({ id: id!, data });
        setSaved(data);
        setForm(data);
        toast.success("Agent saved");
      }
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't save the agent"));
    }
  }

  if (!isNew && agent.isError) return <ErrorBanner error={agent.error} onRetry={() => agent.refetch()} />;
  if (!isNew && agent.isLoading) return <Skeleton className="h-[70vh] w-full" />;

  return (
    <div className="space-y-4">
      {/* Top bar */}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="icon" onClick={() => navigate("/agents")} aria-label="Back to agents">
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <Input
          value={form.name}
          onChange={(e) => update("name", e.target.value)}
          disabled={!canEdit}
          className="h-9 max-w-xs font-heading text-lg font-semibold"
          aria-label="Agent name"
        />
        {dirty && <span className="text-xs text-muted-foreground">Unsaved changes</span>}
        <div className="ml-auto flex gap-2">
          {!isNew && (
            <Button variant="outline" onClick={() => setTestCallOpen(true)} disabled={dirty} title={dirty ? "Save first" : undefined}>
              <Phone className="h-4 w-4" /> Test agent
            </Button>
          )}
          {canEdit && (
            <Button variant="gradient" onClick={handleSave} disabled={saving || (!dirty && !isNew)}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {isNew ? "Create agent" : "Save"}
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[170px_minmax(0,1fr)_340px]">
        {/* Left nav */}
        <nav className="flex gap-1 overflow-x-auto lg:flex-col">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={cn(
                "flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
                tab === key ? "bg-accent font-medium text-foreground" : "text-muted-foreground hover:bg-accent/60"
              )}
            >
              <Icon className="h-4 w-4" /> {label}
              {key === "variables" && variables.length > 0 && (
                <span className="ml-auto rounded-full bg-muted px-1.5 text-[10px]">{variables.length}</span>
              )}
            </button>
          ))}
        </nav>

        {/* Center */}
        <div className="min-w-0 rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)] sm:p-6">
          {tab === "instructions" && (
            <div className="space-y-6">
              <ScriptField
                label="Greeting"
                hint="Spoken word for word as soon as the call connects."
                value={form.welcome_message}
                onChange={(v) => update("welcome_message", v)}
                disabled={!canEdit}
                rows={3}
              />
              <ScriptField
                label="Instructions"
                hint="What the agent knows and how it behaves. Use ## for sections, - for bullets, {name} for placeholders."
                value={form.system_prompt}
                onChange={(v) => update("system_prompt", v)}
                disabled={!canEdit}
                rows={24}
              />
            </div>
          )}

          {tab === "variables" && (
            <VariablesTab
              names={variables}
              values={form.variables}
              disabled={!canEdit}
              onChange={(name, value) => update("variables", { ...form.variables, [name]: value })}
            />
          )}

          {tab === "tools" && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Built-in tools the agent can use on every call. Mention them by name in the instructions to say when.
              </p>
              {AGENT_TOOLS.map((t) => (
                <div key={t} className="rounded-lg border border-border p-3">
                  <ToolChip name={t} />
                  <p className="mt-1.5 text-sm text-muted-foreground">{TOOL_HELP[t]}</p>
                </div>
              ))}
            </div>
          )}

          {tab === "brochure" &&
            (isNew || !agent.data ? (
              <p className="text-sm text-muted-foreground">Create the agent first, then add its brochure here.</p>
            ) : (
              <BrochureTab agent={agent.data} canEdit={canEdit} blocked={dirty} />
            ))}

          {tab === "calendar" &&
            (isNew || !agent.data ? (
              <p className="text-sm text-muted-foreground">Create the agent first, then connect its calendar here.</p>
            ) : (
              <CalendarTab agentId={agent.data.id} canEdit={canEdit} />
            ))}

          {tab === "settings" && (
            <div className="max-w-md space-y-5">
              <div className="space-y-1.5">
                <Label>Description</Label>
                <Input value={form.description} onChange={(e) => update("description", e.target.value)} disabled={!canEdit} placeholder="What this agent is for" />
              </div>
              <div className="space-y-1.5">
                <Label>Language</Label>
                <LanguageSelect value={form.language} onChange={(v) => setForm((f) => ({ ...f, language: v, voice_id: "" }))} />
                <p className="text-xs text-muted-foreground">Write the greeting in this language. A campaign can override it.</p>
              </div>
              <div className="space-y-1.5">
                <Label>Voice</Label>
                <VoiceSelect language={form.language} value={form.voice_id} onChange={(v) => update("voice_id", v)} />
              </div>
              <div className="space-y-1.5">
                <Label>Creativity: {form.llm_temperature.toFixed(1)}</Label>
                <Slider min={0} max={1.2} step={0.1} value={[form.llm_temperature]} onValueChange={([v]) => update("llm_temperature", v)} disabled={!canEdit} />
                <p className="text-xs text-muted-foreground">Lower = sticks closely to the script. Higher = more varied wording.</p>
              </div>
              <div className="space-y-1.5">
                <Label>Speaking speed: {form.speech_pace.toFixed(2)}x</Label>
                <Slider min={0.7} max={1.5} step={0.05} value={[form.speech_pace]} onValueChange={([v]) => update("speech_pace", v)} disabled={!canEdit} />
                <p className="text-xs text-muted-foreground">1.0 is normal. Raise it if the voice sounds slow.</p>
              </div>
              <div className="space-y-1.5">
                <Label>Maximum call length (minutes)</Label>
                <Input
                  type="number" min={1} max={30}
                  value={Math.round(form.max_call_duration_seconds / 60)}
                  onChange={(e) => update("max_call_duration_seconds", Math.max(1, Math.min(30, Number(e.target.value) || 1)) * 60)}
                  disabled={!canEdit}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="transfer-number">Transfer number</Label>
                <Input
                  id="transfer-number" type="tel" placeholder="+91 98765 43210"
                  value={form.transfer_number}
                  onChange={(e) => update("transfer_number", e.target.value)}
                  disabled={!canEdit}
                />
                <p className="text-xs text-muted-foreground">
                  When a customer asks for a person, the agent rings this number and connects them. Leave empty to turn transfers off.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Right: Customise with AI */}
        {canEdit && (
          <CustomizePanel
            greeting={form.welcome_message}
            instructions={form.system_prompt}
            onApply={(greeting, instructions) => setForm((f) => ({ ...f, welcome_message: greeting, system_prompt: instructions }))}
          />
        )}
      </div>

      {!isNew && agent.data && (
        <TestCallDialog agent={testCallOpen ? agent.data : null} onOpenChange={() => setTestCallOpen(false)} />
      )}
    </div>
  );
}

/** The file the agent emails when a customer agrees to receive it on a call. */
function BrochureTab({ agent, canEdit, blocked }: { agent: AgentTemplate; canEdit: boolean; blocked: boolean }) {
  const qc = useQueryClient();
  const meta = useLeadsMeta();
  const fileRef = useRef<HTMLInputElement>(null);
  const [subject, setSubject] = useState(agent.brochure_email_subject ?? "");
  const [body, setBody] = useState(agent.brochure_email_body ?? "");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSubject(agent.brochure_email_subject ?? "");
    setBody(agent.brochure_email_body ?? "");
  }, [agent.brochure_email_subject, agent.brochure_email_body]);

  // Brochure changes reload the agent, which would wipe unsaved script edits.
  const disabled = !canEdit || blocked || busy;
  const textDirty = subject !== (agent.brochure_email_subject ?? "") || body !== (agent.brochure_email_body ?? "");

  async function run(action: () => Promise<unknown>, ok: string) {
    setBusy(true);
    try {
      await action();
      await qc.invalidateQueries({ queryKey: ["agents"] });
      toast.success(ok);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't update the brochure"));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className="max-w-xl space-y-5">
      <p className="text-sm text-muted-foreground">
        When a customer agrees on the call to receive your brochure, the agent notes it and the brochure is emailed to
        them from your company mailbox right after the call. It shows on the lead's timeline.
      </p>

      {meta.data && !meta.data.email_enabled && (
        <p className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
          Your mailbox isn't connected yet, so the agent won't offer the brochure. An admin can connect it in{" "}
          <Link to="/settings" className="underline">Settings → Integrations</Link>.
        </p>
      )}
      {blocked && <p className="text-sm text-muted-foreground">Save your script changes first.</p>}

      <div className="space-y-1.5">
        <Label>Brochure file</Label>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) run(() => agentsApi.uploadBrochure(agent.id, f), "Brochure uploaded");
          }}
        />
        {agent.brochure_filename ? (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm">
            <Paperclip className="h-4 w-4 text-muted-foreground" />
            <span className="mr-auto font-medium">{agent.brochure_filename}</span>
            <Button size="sm" variant="ghost" onClick={() => agentsApi.downloadBrochure(agent.id, agent.brochure_filename!).catch(() => toast.error("Download failed"))}>
              <Download className="h-4 w-4" /> Download
            </Button>
            <Button size="sm" variant="outline" disabled={disabled} onClick={() => fileRef.current?.click()}>Replace</Button>
            <Button size="sm" variant="outline" disabled={disabled} onClick={() => run(() => agentsApi.removeBrochure(agent.id), "Brochure removed")}>
              <Trash2 className="h-4 w-4" /> Remove
            </Button>
          </div>
        ) : (
          <div>
            <Button variant="outline" disabled={disabled} onClick={() => fileRef.current?.click()}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Upload brochure
            </Button>
            <p className="mt-1.5 text-xs text-muted-foreground">PDF, PNG or JPG, up to 10 MB.</p>
          </div>
        )}
      </div>

      {agent.brochure_filename && (
        <>
          <div className="space-y-1.5">
            <Label htmlFor="brochure-subject">Email subject</Label>
            <Input id="brochure-subject" value={subject} onChange={(e) => setSubject(e.target.value)} disabled={!canEdit} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="brochure-body">Email message</Label>
            <Textarea id="brochure-body" rows={7} value={body} onChange={(e) => setBody(e.target.value)} disabled={!canEdit} />
            <p className="text-xs text-muted-foreground">{"{name}"} and {"{company}"} are filled in for each customer.</p>
          </div>
          <Button
            variant="gradient"
            disabled={disabled || !textDirty || !subject.trim() || !body.trim()}
            onClick={() => run(() => agentsApi.update(agent.id, { brochure_email_subject: subject, brochure_email_body: body }), "Email saved")}
          >
            Save email
          </Button>
        </>
      )}
    </div>
  );
}

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** The Google Calendar this agent checks and books meetings into, live on the call. */
function CalendarTab({ agentId, canEdit }: { agentId: string; canEdit: boolean }) {
  const qc = useQueryClient();
  const cal = useAgentCalendar(agentId);
  const [settings, setSettings] = useState<CalendarSettings | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (cal.data) setSettings(cal.data.settings);
  }, [cal.data]);

  async function run(action: () => Promise<unknown>, ok: string) {
    setBusy(true);
    try {
      await action();
      await qc.invalidateQueries({ queryKey: ["agent-calendar", agentId] });
      toast.success(ok);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't update the calendar"));
    } finally {
      setBusy(false);
    }
  }

  async function connect() {
    // Open the tab now: browsers block pop-ups opened after an await.
    const tab = window.open("", "_blank");
    setBusy(true);
    try {
      const { data } = await agentsApi.connectCalendar(agentId);
      if (tab) tab.location.href = data.url;
      else window.location.href = data.url;
    } catch (err) {
      tab?.close();
      toast.error(apiErrorMessage(err, "Couldn't start Google sign-in"));
    } finally {
      setBusy(false);
    }
  }

  if (cal.isLoading || !settings) return <Skeleton className="h-40 max-w-xl" />;
  if (cal.isError || !cal.data) return <ErrorBanner error={cal.error} onRetry={() => cal.refetch()} />;
  const data = cal.data;
  const dirty = JSON.stringify(settings) !== JSON.stringify(data.settings);
  const set = <K extends keyof CalendarSettings>(k: K, v: CalendarSettings[K]) => setSettings((s) => s && { ...s, [k]: v });

  return (
    <div className="max-w-xl space-y-5">
      <p className="text-sm text-muted-foreground">
        When a customer agrees to a meeting, the agent checks this Google Calendar for free times, offers them, and books
        the one they pick, with a Google Meet link. Google emails the invite to the customer when we have their email.
        The meeting shows on the lead.
      </p>

      {!data.available ? (
        <p className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
          Google Calendar isn't switched on for this platform yet. Without it the agent just notes the time the customer
          asked for.
        </p>
      ) : data.connected ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm">
          <CalendarDays className="h-4 w-4 text-primary" />
          <span className="mr-auto">
            Connected to <span className="font-medium">{data.email ?? "Google Calendar"}</span>
          </span>
          <Button size="sm" variant="outline" disabled={!canEdit || busy} onClick={connect}>Reconnect</Button>
          <Button size="sm" variant="outline" disabled={!canEdit || busy} onClick={() => run(() => agentsApi.disconnectCalendar(agentId), "Calendar disconnected")}>
            Disconnect
          </Button>
        </div>
      ) : (
        <div>
          <Button variant="outline" disabled={!canEdit || busy} onClick={connect}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarDays className="h-4 w-4" />} Connect Google Calendar
          </Button>
          <p className="mt-1.5 text-xs text-muted-foreground">
            Sign in with the Google account whose calendar should get the meetings, then come back to this tab.
          </p>
        </div>
      )}

      {data.available && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="cal-len">Meeting length (min)</Label>
              <Input id="cal-len" type="number" min={15} max={240} step={15} value={settings.duration_minutes}
                onChange={(e) => set("duration_minutes", Number(e.target.value) || 30)} disabled={!canEdit} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cal-start">Day starts</Label>
              <Input id="cal-start" type="time" value={settings.day_start} onChange={(e) => set("day_start", e.target.value)} disabled={!canEdit} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cal-end">Day ends</Label>
              <Input id="cal-end" type="time" value={settings.day_end} onChange={(e) => set("day_end", e.target.value)} disabled={!canEdit} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Working days</Label>
            <div className="flex flex-wrap gap-1.5">
              {WEEKDAYS.map((d, i) => {
                const on = settings.days.includes(i);
                return (
                  <Button key={d} size="sm" variant={on ? "default" : "outline"} aria-pressed={on} disabled={!canEdit}
                    onClick={() => set("days", on ? settings.days.filter((x) => x !== i) : [...settings.days, i].sort())}>
                    {d}
                  </Button>
                );
              })}
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="cal-tz">Timezone</Label>
            <Input id="cal-tz" value={settings.timezone} onChange={(e) => set("timezone", e.target.value)} disabled={!canEdit} />
            <p className="text-xs text-muted-foreground">The agent never offers a slot less than 1 hour away.</p>
          </div>
          <Button variant="gradient" disabled={!canEdit || busy || !dirty || settings.days.length === 0}
            onClick={() => run(() => agentsApi.saveCalendar(agentId, settings), "Calendar settings saved")}>
            Save
          </Button>
        </>
      )}
    </div>
  );
}

/** Rendered like a document (placeholders and tools as chips); click Edit to change the raw text. */
function ScriptField({
  label, hint, value, onChange, disabled, rows,
}: {
  label: string; hint: string; value: string; onChange: (v: string) => void; disabled: boolean; rows: number;
}) {
  const [editing, setEditing] = useState(false);
  return (
    <section className="space-y-2">
      <div className="flex items-end justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-muted-foreground underline decoration-dotted underline-offset-4">{label}</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>
        </div>
        {!disabled && (
          <Button variant="ghost" size="sm" onClick={() => setEditing((e) => !e)}>
            {editing ? <><Check className="h-3.5 w-3.5" /> Done</> : <><Pencil className="h-3.5 w-3.5" /> Edit</>}
          </Button>
        )}
      </div>
      {editing ? (
        <Textarea value={value} onChange={(e) => onChange(e.target.value)} rows={rows} className="font-mono text-[13px] leading-relaxed" autoFocus />
      ) : (
        <div
          className={cn("rounded-lg px-1 py-1", !disabled && "cursor-text hover:bg-accent/30")}
          onClick={() => !disabled && setEditing(true)}
        >
          {value.trim() ? <ScriptView text={value} /> : <p className="text-sm italic text-muted-foreground">Empty — click to write, or ask the AI on the right.</p>}
        </div>
      )}
    </section>
  );
}

const INLINE_RE = new RegExp(`(\\{[A-Za-z_][A-Za-z0-9_]*\\}|\\b(?:${AGENT_TOOLS.join("|")})\\b)`, "g");

function Inline({ text }: { text: string }) {
  const parts = text.split(INLINE_RE);
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 0 ? p : p.startsWith("{") ? <VarChip key={i} name={p.slice(1, -1)} /> : <ToolChip key={i} name={p} />
      )}
    </>
  );
}

function VarChip({ name }: { name: string }) {
  return (
    <span className="mx-0.5 inline-flex items-center rounded-md bg-muted px-1.5 py-0.5 font-mono text-[12px] text-foreground">
      <span className="mr-1 text-muted-foreground">{"{}"}</span>{name}
    </span>
  );
}

function ToolChip({ name }: { name: string }) {
  return (
    <span className="mx-0.5 inline-flex items-center gap-1 rounded-md bg-warning/15 px-1.5 py-0.5 font-mono text-[12px] text-foreground">
      <Wrench className="h-3 w-3 text-warning" />{name}
    </span>
  );
}

/** Just enough markdown for agent scripts: #/##/### headings, nested "- " bullets, paragraphs. */
function ScriptView({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  text.split("\n").forEach((raw, i) => {
    const line = raw.trimEnd();
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    const bullet = /^(\s*)[-*]\s+(.*)$/.exec(line);
    if (heading) {
      const sub = heading[1].length === 3;
      blocks.push(
        <p key={i} className={cn("font-heading", sub ? "mt-4 text-base font-semibold" : "mt-6 text-xl font-semibold first:mt-0")}>
          <Inline text={heading[2]} />
        </p>
      );
    } else if (bullet) {
      const depth = Math.min(3, Math.floor(bullet[1].length / 2));
      blocks.push(
        <div key={i} className="flex gap-2 py-0.5 text-sm leading-relaxed" style={{ paddingLeft: `${depth * 1.25}rem` }}>
          <span className="select-none text-muted-foreground">{depth ? "◦" : "•"}</span>
          <span><Inline text={bullet[2]} /></span>
        </div>
      );
    } else if (line.trim()) {
      blocks.push(<p key={i} className="py-0.5 text-sm leading-relaxed"><Inline text={line} /></p>);
    }
  });
  return <div>{blocks}</div>;
}

function VariablesTab({
  names, values, disabled, onChange,
}: {
  names: string[]; values: Record<string, string>; disabled: boolean; onChange: (name: string, value: string) => void;
}) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Every <VarChip name="placeholder" /> in the greeting and instructions. For each call it's filled from the
        contact's CSV column with the same name (e.g. a <span className="font-mono">userName</span> or
        "User Name" column), otherwise from the default value here.
      </p>
      {names.length === 0 ? (
        <p className="text-sm italic text-muted-foreground">No placeholders yet. Write one as {"{name}"} in the instructions.</p>
      ) : (
        <div className="divide-y divide-border rounded-lg border border-border">
          {names.map((name) => (
            <div key={name} className="grid items-center gap-2 p-3 sm:grid-cols-[220px_1fr]">
              <VarChip name={name} />
              <Input
                value={values[name] ?? ""}
                onChange={(e) => onChange(name, e.target.value)}
                disabled={disabled}
                placeholder="Default value (optional — CSV column wins)"
              />
            </div>
          ))}
        </div>
      )}
      <div className="rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">
        Filled automatically on every call: {SYSTEM_VARIABLES.map((v) => <VarChip key={v} name={v} />)} (today's date; time_greeting = Good morning / afternoon / evening).
      </div>
    </div>
  );
}

function CustomizePanel({
  greeting, instructions, onApply,
}: {
  greeting: string; instructions: string; onApply: (greeting: string, instructions: string) => void;
}) {
  const customize = useCustomizeAgent();
  const [request, setRequest] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);

  async function send() {
    const text = request.trim();
    if (!text || customize.isPending) return;
    setRequest("");
    const before = { greeting, instructions };
    setTurns((t) => [...t, { request: text }]);
    try {
      const r = await customize.mutateAsync({ greeting, instructions, request: text });
      onApply(r.greeting, r.instructions);
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, summary: r.summary || "Done.", undo: before } : turn)));
    } catch (err) {
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, error: apiErrorMessage(err, "Couldn't customise") } : turn)));
    }
  }

  function undo(index: number) {
    const turn = turns[index];
    if (!turn.undo) return;
    onApply(turn.undo.greeting, turn.undo.instructions);
    setTurns((t) => t.map((x, i) => (i === index ? { ...x, undo: undefined, summary: `${x.summary} (undone)` } : x)));
  }

  return (
    <aside className="flex max-h-[80vh] flex-col rounded-xl border border-border bg-card shadow-[var(--shadow-card)] lg:sticky lg:top-4">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Sparkles className="h-4 w-4 text-primary" />
        <p className="text-sm font-semibold">Customise with AI</p>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto p-4 text-sm">
        {turns.length === 0 && (
          <div className="space-y-2 text-muted-foreground">
            <p>Describe a change and the AI rewrites the greeting and instructions — placeholders included.</p>
            <p className="text-xs">Try: "This agent sells steel to construction firms in Pune — rewrite it for that", "Make her more formal, English only", or "Add a section for the objection: we already have a vendor".</p>
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className="space-y-2">
            <p className="ml-6 rounded-xl bg-accent px-3 py-2">{t.request}</p>
            {t.error ? (
              <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-destructive">{t.error}</p>
            ) : t.summary ? (
              <div className="space-y-1.5">
                <p className="leading-relaxed">{t.summary}</p>
                <p className="text-xs text-muted-foreground">Applied to the editor — review it, then Save.</p>
                {t.undo && (
                  <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => undo(i)}>
                    <Undo2 className="h-3 w-3" /> Undo
                  </Button>
                )}
              </div>
            ) : (
              <p className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Rewriting… this can take up to a minute.
              </p>
            )}
          </div>
        ))}
      </div>
      <div className="border-t border-border p-3">
        <Textarea
          value={request}
          onChange={(e) => setRequest(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          rows={3}
          placeholder="Ask for a change…"
          disabled={customize.isPending}
        />
        <Button variant="gradient" size="sm" className="mt-2 w-full" onClick={() => void send()} disabled={customize.isPending || !request.trim()}>
          {customize.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Apply change
        </Button>
      </div>
    </aside>
  );
}
