import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, Check, ChevronLeft, ChevronRight, Download, Loader2, Rocket } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageHeader } from "@/components/shared/PageHeader";
import { ContactsUploader } from "@/components/shared/ContactsUploader";
import { LanguageSelect, VoiceSelect } from "@/components/shared/VoiceFields";
import {
  useAgents,
  useCampaignPreview,
  useCreateCampaign,
  useLaunchCampaign,
  useMyTrunks,
  useUploadContacts,
} from "@/lib/hooks";
import { apiErrorMessage } from "@/lib/api";
import { SYSTEM_VARIABLES, findVariables } from "@/lib/agentTemplate";
import { languageLabel } from "@/lib/languages";
import { cn } from "@/lib/utils";

const STEPS = ["Campaign", "Upload CSV", "Preview", "Launch"];

export default function CampaignNew() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [contactCount, setContactCount] = useState<number | null>(null);
  const [form, setForm] = useState({
    name: "",
    agent_template_id: "",
    language: "", // "" = the agent's own language
    voice_id: "", // "" = the agent's own voice (or the language's default)
    sip_trunk_id: "",
  });

  const agents = useAgents();
  const trunks = useMyTrunks();
  const createCampaign = useCreateCampaign();
  const uploadContacts = useUploadContacts();
  const launchCampaign = useLaunchCampaign();
  const preview = useCampaignPreview(step >= 2 ? campaignId : null);

  const usableAgents = (agents.data ?? []).filter((a) => a.access_status === "approved");
  const agent = usableAgents.find((a) => a.id === form.agent_template_id);
  const language = form.language || agent?.language || "hinglish";
  const csvColumns = agent
    ? findVariables(agent.welcome_message, agent.system_prompt).filter((v) => !SYSTEM_VARIABLES.includes(v))
    : [];
  const trunkOptions = trunks.data ?? [];

  function update<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function createDraft() {
    if (!form.name.trim()) return toast.error("Give the campaign a name");
    if (!form.agent_template_id) return toast.error("Select an AI agent");
    if (!form.sip_trunk_id && !trunkOptions.some((t) => t.is_default)) {
      return toast.error("Select the phone number to call from");
    }
    try {
      const res = await createCampaign.mutateAsync({
        name: form.name.trim(),
        agent_template_id: form.agent_template_id,
        sip_trunk_id: form.sip_trunk_id || undefined,
        language: form.language || undefined,
        voice_id: form.voice_id || undefined,
      });
      setCampaignId(res.data.id);
      setStep(1);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't create the campaign"));
    }
  }

  async function handleFile(file: File) {
    if (!campaignId) return;
    try {
      const res = await uploadContacts.mutateAsync({ id: campaignId, file });
      setContactCount(res.data.count);
      toast.success(res.data.message || `${res.data.count} contacts uploaded`);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't upload contacts"));
    }
  }

  function downloadCsvTemplate() {
    const header = ["phone", ...csvColumns].join(",");
    const url = URL.createObjectURL(new Blob([header + "\n"], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(agent?.name || "contacts").replace(/\W+/g, "-").toLowerCase()}-template.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleLaunch() {
    if (!campaignId) return;
    try {
      await launchCampaign.mutateAsync(campaignId);
      toast.success("Campaign launched!");
      navigate(`/campaigns/${campaignId}`);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't launch the campaign"));
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="New Campaign" description="Pick an agent, upload your contacts, check the preview and launch." />

      {/* Stepper */}
      <div className="flex items-center">
        {STEPS.map((label, i) => (
          <div key={label} className="flex flex-1 items-center last:flex-none">
            <div className="flex flex-col items-center gap-1">
              <div
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-full border text-sm font-medium",
                  i < step ? "border-primary bg-primary text-primary-foreground"
                    : i === step ? "border-primary text-primary" : "border-border text-muted-foreground"
                )}
              >
                {i < step ? <Check className="h-4 w-4" /> : i + 1}
              </div>
              <span className={cn("text-xs", i === step ? "font-medium text-foreground" : "text-muted-foreground")}>{label}</span>
            </div>
            {i < STEPS.length - 1 && <div className={cn("mx-2 mb-5 h-px flex-1", i < step ? "bg-primary" : "bg-border")} />}
          </div>
        ))}
      </div>

      <Card>
        <CardContent className="space-y-5 pt-6">
          {step === 0 && (
            <>
              <div className="space-y-1.5">
                <Label>Campaign name</Label>
                <Input value={form.name} onChange={(e) => update("name", e.target.value)} placeholder="e.g. Pune steel buyers — October" />
              </div>
              <div className="space-y-1.5">
                <Label>AI agent</Label>
                <Select
                  value={form.agent_template_id}
                  onValueChange={(v) => setForm((f) => ({ ...f, agent_template_id: v, language: "", voice_id: "" }))}
                >
                  <SelectTrigger><SelectValue placeholder={agents.isLoading ? "Loading…" : "Select an agent"} /></SelectTrigger>
                  <SelectContent>
                    {usableAgents.map((a) => (
                      <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {!agents.isLoading && usableAgents.length === 0 && (
                  <p className="text-xs text-muted-foreground">
                    No agents yet — <Link to="/agents/new" className="text-primary hover:underline">create one</Link> first.
                  </p>
                )}
              </div>
              <div className="grid gap-5 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>Language</Label>
                  <LanguageSelect
                    value={form.language}
                    onChange={(v) => setForm((f) => ({ ...f, language: v, voice_id: "" }))}
                    inheritLabel={agent ? `Agent's own (${languageLabel(agent.language)})` : "Agent's own language"}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Voice</Label>
                  <VoiceSelect
                    language={language}
                    value={form.voice_id}
                    onChange={(v) => update("voice_id", v)}
                    emptyLabel={form.language ? "Default voice for this language" : "Agent's own voice"}
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Phone number</Label>
                {trunks.isLoading ? (
                  <p className="text-xs text-muted-foreground">Loading numbers…</p>
                ) : trunkOptions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No phone number connected yet — an admin can add one under Phone Numbers.
                  </p>
                ) : (
                  <Select value={form.sip_trunk_id || "default"} onValueChange={(v) => update("sip_trunk_id", v === "default" ? "" : v)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {trunkOptions.some((t) => t.is_default) && <SelectItem value="default">Default number</SelectItem>}
                      {trunkOptions.map((t) => (
                        <SelectItem key={t.id} value={t.id}>{t.caller_id} — {t.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
              <div className="flex justify-end">
                <Button variant="gradient" onClick={createDraft} disabled={createCampaign.isPending}>
                  {createCampaign.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  Continue <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <div className="space-y-2 text-sm">
                <p>
                  Your CSV needs a <span className="font-mono">phone</span> column. Add a column for each of this agent's
                  placeholders so every call is personalised — any you leave out use the agent's default value.
                </p>
                {csvColumns.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {csvColumns.map((c) => (
                      <span key={c} className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-xs">{c}</span>
                    ))}
                  </div>
                )}
                <Button variant="outline" size="sm" onClick={downloadCsvTemplate}>
                  <Download className="h-3.5 w-3.5" /> Download CSV template
                </Button>
              </div>
              <ContactsUploader onFile={handleFile} uploading={uploadContacts.isPending} count={contactCount} />
              <StepNav onBack={() => setStep(0)} backDisabled onNext={() => setStep(2)} nextDisabled={!contactCount} />
            </>
          )}

          {step === 2 && (
            <>
              {preview.isLoading ? (
                <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Building preview…</p>
              ) : preview.isError ? (
                <p className="text-sm text-destructive">{apiErrorMessage(preview.error, "Couldn't load the preview")}</p>
              ) : preview.data && (
                <div className="space-y-4">
                  {preview.data.missing.length > 0 ? (
                    <div className="flex gap-2 rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 text-sm">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                      <span>
                        Some contacts have no value for{" "}
                        {preview.data.missing.map((m) => <span key={m} className="mx-0.5 rounded bg-muted px-1 font-mono text-xs">{m}</span>)}
                        — those calls will leave it blank. Add the column to your CSV, or set a default value on the agent.
                      </span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm">
                      <Check className="h-4 w-4 text-success" /> Every placeholder has a value for all {preview.data.total_contacts} contacts.
                    </div>
                  )}
                  {preview.data.items.map((item) => (
                    <div key={item.contact_id} className="space-y-2 rounded-lg border border-border p-4">
                      <p className="text-sm font-medium">{item.name} <span className="font-normal text-muted-foreground">· {item.phone}</span></p>
                      <p className="rounded-md bg-muted/50 px-3 py-2 text-sm">“{item.welcome_message}”</p>
                      <details className="text-sm">
                        <summary className="cursor-pointer text-xs text-muted-foreground">Show the full instructions for this call</summary>
                        <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap rounded-md bg-muted/50 p-3 font-sans text-xs leading-relaxed">{item.system_prompt}</pre>
                      </details>
                    </div>
                  ))}
                </div>
              )}
              <StepNav onBack={() => setStep(1)} onNext={() => setStep(3)} nextDisabled={!preview.data} />
            </>
          )}

          {step === 3 && (
            <>
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <Summary label="Campaign" value={form.name} />
                <Summary label="AI agent" value={agent?.name ?? "—"} />
                <Summary label="Language" value={languageLabel(language)} />
                <Summary label="Contacts" value={String(contactCount ?? 0)} />
                <Summary
                  label="Calling from"
                  value={trunkOptions.find((t) => t.id === form.sip_trunk_id)?.caller_id ?? "Default number"}
                />
              </dl>
              <p className="text-xs text-muted-foreground">
                Calls go out within the campaign's calling hours. You can pause it any time from the campaign page.
              </p>
              <div className="flex justify-between">
                <Button variant="outline" onClick={() => setStep(2)}><ChevronLeft className="h-4 w-4" /> Back</Button>
                <Button variant="gradient" onClick={handleLaunch} disabled={launchCampaign.isPending}>
                  {launchCampaign.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
                  Launch campaign
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StepNav({ onBack, onNext, nextDisabled, backDisabled }: {
  onBack: () => void; onNext: () => void; nextDisabled?: boolean; backDisabled?: boolean;
}) {
  return (
    <div className="flex justify-between">
      {/* The draft already exists after step 1, so going back there would create a second one */}
      <Button variant="outline" onClick={onBack} disabled={backDisabled}><ChevronLeft className="h-4 w-4" /> Back</Button>
      <Button variant="gradient" onClick={onNext} disabled={nextDisabled}>Continue <ChevronRight className="h-4 w-4" /></Button>
    </div>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-muted/40 px-3 py-2">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}
