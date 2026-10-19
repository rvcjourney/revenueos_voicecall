import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Loader2, TestTube } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageHeader } from "@/components/shared/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { LANGUAGES } from "@/lib/languages";
import { SARVAM_VOICES, ELEVENLABS_VOICES } from "@/lib/voiceCatalog";
import { useAgents, useMyTrunks } from "@/lib/hooks";
import { agentsApi, apiErrorMessage } from "@/lib/api";

// Real, working model names confirmed against the installed livekit-plugins-sarvam
// SDK (see backend/app/api/agents.py's own copy of this list, enforced server-side).
const TTS_PROVIDERS = ["elevenlabs", "sarvam", "cartesia", "chatterbox"];
const SARVAM_TTS_MODELS = ["bulbul:v2", "bulbul:v3-beta", "bulbul:v3"];
const SARVAM_STT_MODELS = ["saarika:v2.5", "saaras:v2.5", "saaras:v3"];
const LLM_PROVIDERS = ["groq", "sarvam"];
const SARVAM_LLM_MODELS = ["sarvam-m", "sarvam-30b", "sarvam-105b"];

// Trial different STT/LLM/TTS provider and model combinations on a real test
// call, without creating or editing a saved AI Agent -- everything here
// overrides the chosen agent's own setup for this one call only.
export default function Testing() {
  const agents = useAgents();
  const trunks = useMyTrunks();
  const [agentId, setAgentId] = useState("");
  const [language, setLanguage] = useState(""); // "" = use the agent's own language
  const [trunkId, setTrunkId] = useState("");
  const [phone, setPhone] = useState("+91");

  const [ttsProvider, setTtsProvider] = useState(""); // "" = use the agent's own
  const [voiceId, setVoiceId] = useState("");
  const [ttsModel, setTtsModel] = useState(""); // Sarvam only
  const [sttModel, setSttModel] = useState(""); // Sarvam is the only STT engine wired up
  const [llmProvider, setLlmProvider] = useState(""); // "" = groq (the agent's own)
  const [llmModel, setLlmModel] = useState("");

  const [loading, setLoading] = useState(false);
  const [lastCallId, setLastCallId] = useState<string | null>(null);

  const trunkOptions = trunks.data ?? [];
  const selectedTrunk = trunkOptions.find((t) => t.id === trunkId) ?? trunkOptions[0];
  const usableAgents = (agents.data ?? []).filter((a) => a.access_status === "approved");
  const voiceChoices = ttsProvider === "sarvam" ? SARVAM_VOICES : ttsProvider === "elevenlabs" ? ELEVENLABS_VOICES : [];

  async function handleCall() {
    if (!agentId) {
      toast.error("Pick an AI agent to test with");
      return;
    }
    setLoading(true);
    setLastCallId(null);
    try {
      const res = await agentsApi.testCall(agentId, phone, {
        trunk_id: selectedTrunk?.id,
        language: language || undefined,
        voice_provider: ttsProvider || undefined,
        voice_id: voiceId || undefined,
        tts_model: ttsModel || undefined,
        stt_model: sttModel || undefined,
        llm_provider: llmProvider || undefined,
        llm_model: llmModel || undefined,
      });
      setLastCallId(res.data.call_id);
      toast.success("Test call started — it should ring shortly");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't start test call"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <PageHeader
        title="Testing"
        description="Place a real test call trying any combination of language, voice, speech-recognition and LLM — everything here overrides the agent's own setup for this one call only."
      />
      <Card>
        <CardContent className="space-y-4 pt-6">
          <div className="space-y-1.5">
            <Label>AI Agent</Label>
            {agents.isLoading ? (
              <Skeleton className="h-9 w-full" />
            ) : (
              <Select value={agentId} onValueChange={setAgentId}>
                <SelectTrigger><SelectValue placeholder="Select an AI agent" /></SelectTrigger>
                <SelectContent>
                  {usableAgents.map((a) => (
                    <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="space-y-1.5">
            <Label>Language</Label>
            <Select value={language || "agent"} onValueChange={(v) => setLanguage(v === "agent" ? "" : v)}>
              <SelectTrigger><SelectValue placeholder="Use the agent's own language" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="agent">Use the agent's own language</SelectItem>
                {LANGUAGES.map((l) => (
                  <SelectItem key={l.value} value={l.value}>{l.label} · {l.native}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>TTS provider</Label>
              <Select value={ttsProvider || "agent"} onValueChange={(v) => { setTtsProvider(v === "agent" ? "" : v); setVoiceId(""); setTtsModel(""); }}>
                <SelectTrigger><SelectValue placeholder="Use the agent's own" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="agent">Use the agent's own</SelectItem>
                  {TTS_PROVIDERS.map((p) => (
                    <SelectItem key={p} value={p} className="capitalize">{p}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>TTS model</Label>
              <Select
                value={ttsModel || "default"}
                onValueChange={(v) => setTtsModel(v === "default" ? "" : v)}
                disabled={ttsProvider !== "sarvam"}
              >
                <SelectTrigger><SelectValue placeholder="Default" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="default">Default</SelectItem>
                  {SARVAM_TTS_MODELS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                </SelectContent>
              </Select>
              {ttsProvider !== "sarvam" && (
                <p className="text-xs text-muted-foreground">Only Sarvam's TTS model is switchable here.</p>
              )}
            </div>
          </div>

          {voiceChoices.length > 0 && (
            <div className="space-y-1.5">
              <Label>Voice</Label>
              <Select value={voiceId || "default"} onValueChange={(v) => setVoiceId(v === "default" ? "" : v)}>
                <SelectTrigger><SelectValue placeholder="Use the agent's own voice" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="default">Use the agent's own voice</SelectItem>
                  {voiceChoices.map((v) => (
                    <SelectItem key={v.id} value={v.id}>{v.name} ({v.gender})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {ttsModel === "bulbul:v2" && (
                <p className="text-xs text-warning">
                  bulbul:v2 has a different, smaller speaker set — picking an incompatible voice fails the call.
                </p>
              )}
            </div>
          )}

          <div className="space-y-1.5">
            <Label>STT model (speech recognition)</Label>
            <Select value={sttModel || "default"} onValueChange={(v) => setSttModel(v === "default" ? "" : v)}>
              <SelectTrigger><SelectValue placeholder="Default (saaras:v3)" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="default">Default (saaras:v3)</SelectItem>
                {SARVAM_STT_MODELS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">Sarvam is the only speech-recognition engine wired up.</p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>LLM provider</Label>
              <Select value={llmProvider || "agent"} onValueChange={(v) => { setLlmProvider(v === "agent" ? "" : v); setLlmModel(""); }}>
                <SelectTrigger><SelectValue placeholder="Use the agent's own (Groq)" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="agent">Use the agent's own (Groq)</SelectItem>
                  {LLM_PROVIDERS.map((p) => <SelectItem key={p} value={p} className="capitalize">{p}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>LLM model</Label>
              <Select
                value={llmModel || "default"}
                onValueChange={(v) => setLlmModel(v === "default" ? "" : v)}
                disabled={llmProvider !== "sarvam"}
              >
                <SelectTrigger><SelectValue placeholder="Default" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="default">Default</SelectItem>
                  {SARVAM_LLM_MODELS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                </SelectContent>
              </Select>
              {llmProvider !== "sarvam" && (
                <p className="text-xs text-muted-foreground">Groq has one model on this platform — nothing to switch yet.</p>
              )}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>From</Label>
            {trunks.isLoading ? (
              <Skeleton className="h-9 w-full" />
            ) : trunkOptions.length > 0 ? (
              <Select value={selectedTrunk?.id ?? ""} onValueChange={setTrunkId}>
                <SelectTrigger><SelectValue placeholder="Select a number..." /></SelectTrigger>
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

          <Button variant="gradient" onClick={handleCall} disabled={loading || !selectedTrunk}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <TestTube className="h-4 w-4" />}
            Place test call
          </Button>

          {lastCallId && (
            <p className="text-sm text-muted-foreground">
              Call started —{" "}
              <Link to={`/calls/${lastCallId}`} className="text-primary hover:underline">
                view it in Call History
              </Link>{" "}
              once it ends to listen to the recording.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
