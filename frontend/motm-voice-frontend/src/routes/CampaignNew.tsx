import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Check, ChevronLeft, ChevronRight, Loader2, Rocket, Upload, UploadCloud } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { AgentAccessBadge } from "@/components/shared/StatusBadge";
import { PageHeader } from "@/components/shared/PageHeader";
import { useAgents, useCreateCampaign, useFolders, useLaunchCampaign, useMyTrunks, useUpdateCampaign, useUploadContacts } from "@/lib/hooks";
import { apiErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { CampaignGoal } from "@/lib/types";

const STEPS = ["Campaign & Agent", "Contacts", "Schedule", "Review & Launch"];
const DAYS = [
  { value: "mon", label: "Mon" },
  { value: "tue", label: "Tue" },
  { value: "wed", label: "Wed" },
  { value: "thu", label: "Thu" },
  { value: "fri", label: "Fri" },
  { value: "sat", label: "Sat" },
  { value: "sun", label: "Sun" },
];

export default function CampaignNew() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [contactCount, setContactCount] = useState<number | null>(null);

  const [form, setForm] = useState({
    name: "",
    description: "",
    goal: "lead_generation" as CampaignGoal,
    folder_id: "",
    agent_template_id: "",
    sip_trunk_id: "",
    calling_window_start: "10:00",
    calling_window_end: "18:00",
    calling_days: ["mon", "tue", "wed", "thu", "fri"] as string[],
    timezone: "Asia/Kolkata",
    calls_per_minute: 5,
    max_retries: 2,
    retry_after_minutes: 60,
  });

  const folders = useFolders();
  const agents = useAgents();
  const trunks = useMyTrunks();
  const createCampaign = useCreateCampaign();
  const updateCampaign = useUpdateCampaign();
  const uploadContacts = useUploadContacts();
  const launchCampaign = useLaunchCampaign();

  function update<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleStep1Submit() {
    if (!form.name.trim() || !form.agent_template_id) {
      toast.error("Campaign name and AI agent are required");
      return;
    }
    try {
      const res = await createCampaign.mutateAsync({
        name: form.name,
        description: form.description || undefined,
        goal: form.goal,
        folder_id: form.folder_id || undefined,
        agent_template_id: form.agent_template_id,
        sip_trunk_id: form.sip_trunk_id || undefined,
      });
      setCampaignId(res.data.id);
      toast.success("Draft campaign created");
      setStep(1);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't create campaign"));
    }
  }

  async function handleFileUpload(file: File) {
    if (!campaignId) return;
    try {
      const res = await uploadContacts.mutateAsync({ id: campaignId, file });
      setContactCount(res.data.count);
      toast.success(res.data.message || `${res.data.count} contacts uploaded`);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't upload contacts"));
    }
  }

  async function handleScheduleSubmit() {
    if (!campaignId) return;
    try {
      await updateCampaign.mutateAsync({
        id: campaignId,
        data: {
          calling_window_start: form.calling_window_start,
          calling_window_end: form.calling_window_end,
          calling_days: form.calling_days,
          timezone: form.timezone,
          calls_per_minute: form.calls_per_minute,
          max_retries: form.max_retries,
          retry_after_minutes: form.retry_after_minutes,
        },
      });
      setStep(3);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't save schedule"));
    }
  }

  async function handleLaunch() {
    if (!campaignId) return;
    try {
      await launchCampaign.mutateAsync(campaignId);
      toast.success("Campaign launched!");
      navigate(`/campaigns/${campaignId}`);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't launch campaign"));
    }
  }

  const selectedAgent = agents.data?.find((a) => a.id === form.agent_template_id);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="New Campaign" description="Set up an AI voice calling campaign in a few steps." />

      {/* Stepper */}
      <div className="flex items-center">
        {STEPS.map((label, i) => (
          <div key={label} className="flex flex-1 items-center last:flex-none">
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-full border text-xs font-medium",
                  i < step
                    ? "border-primary bg-primary text-primary-foreground"
                    : i === step
                      ? "border-primary text-primary"
                      : "border-border text-muted-foreground"
                )}
              >
                {i < step ? <Check className="h-4 w-4" /> : i + 1}
              </div>
              <span className={cn("hidden text-xs sm:block", i === step ? "font-medium text-foreground" : "text-muted-foreground")}>
                {label}
              </span>
            </div>
            {i < STEPS.length - 1 && <div className={cn("mx-2 h-px flex-1", i < step ? "bg-primary" : "bg-border")} />}
          </div>
        ))}
      </div>

      <Card>
        <CardContent className="space-y-5 pt-6">
          {step === 0 && (
            <div className="space-y-5">
              <div className="space-y-1.5">
                <Label htmlFor="c-name">Campaign name</Label>
                <Input id="c-name" placeholder="Q3 Outbound — Enterprise Leads" value={form.name} onChange={(e) => update("name", e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="c-desc">Description (optional)</Label>
                <Textarea id="c-desc" placeholder="What is this campaign for?" value={form.description} onChange={(e) => update("description", e.target.value)} />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>Goal</Label>
                  <Select value={form.goal} onValueChange={(v) => update("goal", v as CampaignGoal)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="lead_generation">Lead Generation</SelectItem>
                      <SelectItem value="follow_up">Follow Up</SelectItem>
                      <SelectItem value="survey">Survey</SelectItem>
                      <SelectItem value="announcement">Announcement</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Folder (optional)</Label>
                  <Select value={form.folder_id || "none"} onValueChange={(v) => update("folder_id", v === "none" ? "" : v)}>
                    <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">None</SelectItem>
                      {folders.data?.map((f) => (
                        <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label>AI Agent</Label>
                <Select value={form.agent_template_id} onValueChange={(v) => update("agent_template_id", v)}>
                  <SelectTrigger><SelectValue placeholder="Select an AI agent" /></SelectTrigger>
                  <SelectContent>
                    {agents.data?.map((a) => (
                      <SelectItem key={a.id} value={a.id} disabled={a.access_status !== "approved"}>
                        {a.name} {a.access_status !== "approved" ? `(${a.access_status})` : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedAgent && (
                  <div className="flex items-center gap-2 pt-1">
                    <AgentAccessBadge status={selectedAgent.access_status} />
                    <span className="text-xs text-muted-foreground">
                      {selectedAgent.voice_provider} · {selectedAgent.llm_model}
                    </span>
                  </div>
                )}
                {agents.data?.length === 0 && (
                  <p className="text-xs text-muted-foreground">No agents yet. Create one from the AI Agents page first.</p>
                )}
              </div>

              <div className="space-y-1.5">
                <Label>Phone number to call from (optional)</Label>
                <Select value={form.sip_trunk_id || "default"} onValueChange={(v) => update("sip_trunk_id", v === "default" ? "" : v)}>
                  <SelectTrigger><SelectValue placeholder="Use default number" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="default">Use default number</SelectItem>
                    {trunks.data?.map((t) => (
                      <SelectItem key={t.id} value={t.id}>{t.name} · {t.caller_id}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-5">
              <ContactsUploader onFile={handleFileUpload} uploading={uploadContacts.isPending} count={contactCount} />
              <p className="text-xs text-muted-foreground">
                We'll match any column containing "phone" automatically. Name, email, and company are optional — every
                other column becomes a custom field for your agent.
              </p>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="window-start">Calling window start</Label>
                  <Input id="window-start" type="time" value={form.calling_window_start} onChange={(e) => update("calling_window_start", e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="window-end">Calling window end</Label>
                  <Input id="window-end" type="time" value={form.calling_window_end} onChange={(e) => update("calling_window_end", e.target.value)} />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Calling days</Label>
                <div className="flex flex-wrap gap-3">
                  {DAYS.map((d) => (
                    <label key={d.value} className="flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-sm">
                      <Checkbox
                        checked={form.calling_days.includes(d.value)}
                        onCheckedChange={(checked) =>
                          update(
                            "calling_days",
                            checked ? [...form.calling_days, d.value] : form.calling_days.filter((x) => x !== d.value)
                          )
                        }
                      />
                      {d.label}
                    </label>
                  ))}
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="space-y-1.5">
                  <Label htmlFor="cpm">Calls per minute</Label>
                  <Input id="cpm" type="number" min={1} value={form.calls_per_minute} onChange={(e) => update("calls_per_minute", Number(e.target.value))} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="retries">Max retries</Label>
                  <Input id="retries" type="number" min={0} value={form.max_retries} onChange={(e) => update("max_retries", Number(e.target.value))} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="retry-after">Retry after (min)</Label>
                  <Input id="retry-after" type="number" min={1} value={form.retry_after_minutes} onChange={(e) => update("retry_after_minutes", Number(e.target.value))} />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Timezone</Label>
                <Input value={form.timezone} onChange={(e) => update("timezone", e.target.value)} />
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4 text-sm">
              <SummaryRow label="Name" value={form.name} />
              <SummaryRow label="Goal" value={form.goal.replace("_", " ")} />
              <SummaryRow label="Agent" value={selectedAgent?.name ?? "—"} />
              <SummaryRow label="Contacts" value={contactCount !== null ? `${contactCount} uploaded` : "None uploaded"} />
              <SummaryRow label="Calling window" value={`${form.calling_window_start} – ${form.calling_window_end} (${form.timezone})`} />
              <SummaryRow label="Calling days" value={form.calling_days.map((d) => d.toUpperCase()).join(", ") || "—"} />
              <SummaryRow label="Pace" value={`${form.calls_per_minute} calls/min · ${form.max_retries} retries`} />
              {contactCount === 0 || contactCount === null ? (
                <p className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
                  You haven't uploaded any contacts yet — you can launch later from the campaign page once contacts are added.
                </p>
              ) : null}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex items-center justify-between">
        <Button variant="outline" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>
          <ChevronLeft className="h-4 w-4" /> Back
        </Button>

        {step === 0 && (
          <Button variant="gradient" onClick={handleStep1Submit} disabled={createCampaign.isPending}>
            {createCampaign.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Continue <ChevronRight className="h-4 w-4" />
          </Button>
        )}
        {step === 1 && (
          <Button variant="gradient" onClick={() => setStep(2)}>
            Continue <ChevronRight className="h-4 w-4" />
          </Button>
        )}
        {step === 2 && (
          <Button variant="gradient" onClick={handleScheduleSubmit} disabled={updateCampaign.isPending}>
            {updateCampaign.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Continue <ChevronRight className="h-4 w-4" />
          </Button>
        )}
        {step === 3 && (
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => navigate(`/campaigns/${campaignId}`)}>
              Save as draft
            </Button>
            <Button variant="gradient" onClick={handleLaunch} disabled={launchCampaign.isPending || !contactCount}>
              {launchCampaign.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
              Launch now
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border/60 pb-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium capitalize">{value}</span>
    </div>
  );
}

function ContactsUploader({
  onFile,
  uploading,
  count,
}: {
  onFile: (file: File) => void;
  uploading: boolean;
  count: number | null;
}) {
  const [dragOver, setDragOver] = useState(false);

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
      className={cn(
        "flex cursor-pointer flex-col items-center gap-3 rounded-xl border-2 border-dashed p-10 text-center transition-colors",
        dragOver ? "border-primary bg-primary/10" : "border-border hover:bg-muted/30"
      )}
    >
      <input
        type="file"
        accept=".csv,.xlsx,.xls"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
        }}
      />
      {uploading ? (
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      ) : count !== null ? (
        <Check className="h-8 w-8 text-success" />
      ) : (
        <UploadCloud className="h-8 w-8 text-muted-foreground" />
      )}
      <div>
        <p className="text-sm font-medium">
          {count !== null ? `${count} contacts uploaded` : "Drag & drop a CSV or Excel file"}
        </p>
        <p className="text-xs text-muted-foreground">or click to browse — thousands of contacts supported</p>
      </div>
      <Button type="button" variant="outline" size="sm" asChild>
        <span>
          <Upload className="h-3.5 w-3.5" /> {count !== null ? "Replace file" : "Choose file"}
        </span>
      </Button>
    </label>
  );
}
