/**
 * Customer-facing labels for internal voice-provider/LLM-model identifiers.
 *
 * These show up anywhere a customer configures or views their own agent
 * (Agents.tsx, admin/InboundAgents.tsx, CampaignNew.tsx) -- never show the
 * underlying vendor or model name there, only in code/comments/internal
 * (superadmin-only) screens. The value sent to the API is unchanged; this
 * only controls what's rendered.
 */
const VOICE_PROVIDER_LABELS: Record<string, string> = {
  elevenlabs: "Studio (Hindi / Hinglish / English)",
  cartesia: "Lite (English, low-latency)",
  sarvam: "Regional (Indian languages)",
  chatterbox: "Experimental (self-hosted)",
};

const LLM_MODEL_LABELS: Record<string, string> = {
  "qwen/qwen3.6-27b": "QuickHowl Conversational Engine",
};

export function voiceProviderLabel(value?: string | null): string {
  if (!value) return "";
  return VOICE_PROVIDER_LABELS[value] ?? value;
}

export function llmModelLabel(value?: string | null): string {
  if (!value) return "";
  return LLM_MODEL_LABELS[value] ?? value;
}
