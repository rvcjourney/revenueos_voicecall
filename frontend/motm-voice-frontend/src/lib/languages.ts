/**
 * The languages an agent can speak on a call — labels only, for showing a
 * saved value. Which languages are actually available (and their voices) comes
 * from the server: useLanguages() / GET /api/languages (app/core/pipelines.py).
 */
export const LANGUAGES: { value: string; label: string; native: string }[] = [
  { value: "hinglish", label: "Hinglish (Hindi-English mix)", native: "Hinglish" },
  { value: "hindi", label: "Hindi", native: "हिंदी" },
  { value: "english", label: "English (Indian)", native: "English" },
  { value: "marathi", label: "Marathi", native: "मराठी" },
  { value: "tamil", label: "Tamil", native: "தமிழ்" },
  { value: "telugu", label: "Telugu", native: "తెలుగు" },
  { value: "bengali", label: "Bengali", native: "বাংলা" },
  { value: "gujarati", label: "Gujarati", native: "ગુજરાતી" },
  { value: "kannada", label: "Kannada", native: "ಕನ್ನಡ" },
  { value: "punjabi", label: "Punjabi", native: "ਪੰਜਾਬੀ" },
];

export function languageLabel(value?: string | null): string {
  return LANGUAGES.find((l) => l.value === value)?.label ?? value ?? "";
}
