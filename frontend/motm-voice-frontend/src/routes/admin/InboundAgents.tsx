import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Loader2, Pencil, PhoneIncoming, Sparkles, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Slider } from "@/components/ui/slider";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useClonedVoices,
  useCreateInboundAgent,
  useDeleteInboundAgent,
  useInboundAgents,
  useUpdateInboundAgent,
} from "@/lib/hooks";
import { agentsApi, apiErrorMessage } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { InboundAgent, InboundAgentCreate } from "@/lib/types";

const VOICE_PROVIDERS = ["elevenlabs", "cartesia", "sarvam", "chatterbox"];
const LLM_MODELS = ["qwen/qwen3.8-27b"];

const emptyForm: InboundAgentCreate = {
  name: "",
  description: "",
  language: "hinglish",
  welcome_message: "",
  system_prompt: "",
  voice_id: "",
  voice_provider: "elevenlabs",
  llm_model: "qwen/qwen3.8-27b",
  llm_temperature: 0.7,
  max_call_duration_seconds: 600,
};

export default function InboundAgents() {
  const agents = useInboundAgents();
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<InboundAgent | null>(null);

  function openCreate() {
    setEditingAgent(null);
    setEditorOpen(true);
  }
  function openEdit(agent: InboundAgent) {
    setEditingAgent(agent);
    setEditorOpen(true);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Inbound Agents"
        description="AI agents that answer calls arriving on your connected numbers — assign one to a number in Phone Numbers."
        actions={
          <Button variant="gradient" onClick={openCreate}>
            <PhoneIncoming className="h-4 w-4" /> Create inbound agent
          </Button>
        }
      />

      {agents.isError ? (
        <ErrorBanner error={agents.error} onRetry={() => agents.refetch()} />
      ) : agents.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-40 w-full" />)}
        </div>
      ) : agents.data && agents.data.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {agents.data.map((a) => (
            <InboundAgentCard key={a.id} agent={a} onEdit={() => openEdit(a)} />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={PhoneIncoming}
          title="No inbound agents yet"
          description="Create one, then assign it to a connected number in Phone Numbers so it can answer calls."
          action={<Button variant="gradient" onClick={openCreate}>Create inbound agent</Button>}
        />
      )}

      <InboundAgentEditorDialog open={editorOpen} onOpenChange={setEditorOpen} agent={editingAgent} />
    </div>
  );
}

function InboundAgentCard({ agent, onEdit }: { agent: InboundAgent; onEdit: () => void }) {
  const deleteAgent = useDeleteInboundAgent();

  async function handleDelete() {
    if (!confirm(`Delete inbound agent "${agent.name}"? Any number currently assigned to it will stop answering inbound calls.`)) return;
    try {
      await deleteAgent.mutateAsync(agent.id);
      toast.success("Inbound agent deleted");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't delete inbound agent"));
    }
  }

  return (
    <div className="relative flex h-full flex-col overflow-hidden rounded-xl border border-border bg-card shadow-[var(--shadow-card)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow-elevated)]">
      <span className="absolute inset-x-0 top-0 h-1" style={{ backgroundColor: "var(--info)" }} />
      <div className="flex flex-1 flex-col gap-3 p-3.5 pt-4">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[image:var(--gradient-primary)]">
            <PhoneIncoming className="h-4 w-4 text-primary-foreground" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold leading-tight">{agent.name}</p>
            <p className="truncate text-[11px] text-muted-foreground">{agent.llm_model}</p>
          </div>
        </div>

        <p className="text-xs text-muted-foreground">{formatDate(agent.created_at)}</p>

        <div className="mt-auto flex gap-1.5 border-t border-border pt-2.5">
          <Button variant="outline" size="sm" className="flex-1" onClick={onEdit}>
            <Pencil className="h-3.5 w-3.5" /> Edit
          </Button>
          <Button variant="outline" size="icon" onClick={handleDelete} disabled={deleteAgent.isPending}>
            <Trash2 className="h-3.5 w-3.5 text-destructive" />
          </Button>
        </div>
      </div>
    </div>
  );
}

function InboundAgentEditorDialog({
  open,
  onOpenChange,
  agent,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  agent: InboundAgent | null;
}) {
  const [form, setForm] = useState<InboundAgentCreate>(agent ? toFormValues(agent) : emptyForm);
  const [optimizing, setOptimizing] = useState(false);
  const createAgent = useCreateInboundAgent();
  const updateAgent = useUpdateInboundAgent();

  useEffect(() => {
    if (open) {
      setForm(agent ? toFormValues(agent) : emptyForm);
    }
  }, [open, agent]);

  function update<K extends keyof InboundAgentCreate>(key: K, value: InboundAgentCreate[K]) {
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
        toast.success("Inbound agent updated");
      } else {
        await createAgent.mutateAsync(form);
        toast.success("Inbound agent created");
      }
      onOpenChange(false);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't save inbound agent"));
    }
  }

  const saving = createAgent.isPending || updateAgent.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{agent ? "Edit inbound agent" : "Create inbound agent"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Name</Label>
              <Input value={form.name} onChange={(e) => update("name", e.target.value)} placeholder="Support Line" />
            </div>
            <div className="space-y-1.5">
              <Label>Language</Label>
              <Input value={form.language} onChange={(e) => update("language", e.target.value)} placeholder="hinglish" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Description</Label>
            <Input value={form.description} onChange={(e) => update("description", e.target.value)} placeholder="What is this inbound agent for?" />
          </div>
          <div className="space-y-1.5">
            <Label>Welcome message</Label>
            <Textarea value={form.welcome_message} onChange={(e) => update("welcome_message", e.target.value)} placeholder="Namaste! Thanks for calling..." rows={2} />
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>System prompt</Label>
              <Button type="button" variant="ghost" size="sm" onClick={handleOptimize} disabled={optimizing}>
                {optimizing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                Optimize with AI
              </Button>
            </div>
            <Textarea value={form.system_prompt} onChange={(e) => update("system_prompt", e.target.value)} rows={6} placeholder="Describe how the agent should handle inbound calls..." />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Voice provider</Label>
              <Select value={form.voice_provider} onValueChange={(v) => update("voice_provider", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {VOICE_PROVIDERS.map((v) => <SelectItem key={v} value={v} className="capitalize">{v}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Voice ID</Label>
              <Input value={form.voice_id} onChange={(e) => update("voice_id", e.target.value)} placeholder="e.g. Suyash" />
            </div>
          </div>
          <ClonedVoicesSection
            voiceProvider={form.voice_provider}
            onSelectVoice={(voiceId) => update("voice_id", voiceId)}
          />
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
            {agent ? "Save changes" : "Create inbound agent"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ClonedVoicesSection({
  voiceProvider,
  onSelectVoice,
}: {
  voiceProvider?: string;
  onSelectVoice: (voiceId: string) => void;
}) {
  const clonedVoices = useClonedVoices();
  const readyVoices = (clonedVoices.data ?? []).filter((v) => v.status === "ready");

  if (voiceProvider !== "elevenlabs") return null;

  return (
    <div className="space-y-1.5">
      <Label>Use a cloned voice</Label>
      {clonedVoices.isLoading ? (
        <Skeleton className="h-9 w-full" />
      ) : readyVoices.length > 0 ? (
        <Select onValueChange={onSelectVoice}>
          <SelectTrigger><SelectValue placeholder="Pick a cloned voice…" /></SelectTrigger>
          <SelectContent>
            {readyVoices.map((v) => (
              <SelectItem key={v.id} value={v.elevenlabs_voice_id ?? ""}>{v.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : (
        <p className="text-xs text-muted-foreground">
          No cloned voices yet —{" "}
          <Link to="/voice-cloning" className="text-primary hover:underline">
            clone one from the Voice Cloning section
          </Link>{" "}
          to use it here.
        </p>
      )}
    </div>
  );
}

function toFormValues(agent: InboundAgent): InboundAgentCreate {
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
