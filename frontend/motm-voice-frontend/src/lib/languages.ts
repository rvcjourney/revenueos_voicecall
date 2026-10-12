/**
 * The languages an agent can speak on a call.
 *
 * Must stay in sync with agent/languages.py (voice + speech-recognition codes)
 * and the backend's AgentLanguage enum (app/models/agent.py).
 *
 * Hindi, Hinglish and English use the agent's own configured voice. Every other
 * language is spoken by a Sarvam Bulbul voice, which is native to Indian
 * languages — ElevenLabs' Indian voices are Hindi/Indian-English only.
 */
export const LANGUAGES: { value: string; label: string; native: string; sarvamVoice: boolean }[] = [
  { value: "hinglish", label: "Hinglish (Hindi-English mix)", native: "Hinglish", sarvamVoice: false },
  { value: "hindi", label: "Hindi", native: "हिंदी", sarvamVoice: false },
  { value: "english", label: "English (Indian)", native: "English", sarvamVoice: false },
  { value: "marathi", label: "Marathi", native: "मराठी", sarvamVoice: true },
  { value: "tamil", label: "Tamil", native: "தமிழ்", sarvamVoice: true },
  { value: "telugu", label: "Telugu", native: "తెలుగు", sarvamVoice: true },
  { value: "bengali", label: "Bengali", native: "বাংলা", sarvamVoice: true },
  { value: "gujarati", label: "Gujarati", native: "ગુજરાતી", sarvamVoice: true },
  { value: "kannada", label: "Kannada", native: "ಕನ್ನಡ", sarvamVoice: true },
  { value: "punjabi", label: "Punjabi", native: "ਪੰਜਾਬੀ", sarvamVoice: true },
];

export function languageLabel(value?: string | null): string {
  return LANGUAGES.find((l) => l.value === value)?.label ?? value ?? "";
}

export function usesSarvamVoice(value?: string | null): boolean {
  return !!LANGUAGES.find((l) => l.value === value)?.sarvamVoice;
}
