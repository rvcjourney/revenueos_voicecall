import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useClonedVoices, useLanguages } from "@/lib/hooks";

/** Language picker over the languages the owner has enabled. `inheritLabel`
 * adds a "use the agent's own" option (value ""). */
export function LanguageSelect({
  value,
  onChange,
  inheritLabel,
}: {
  value: string;
  onChange: (v: string) => void;
  inheritLabel?: string;
}) {
  const langs = useLanguages();
  return (
    <Select value={value || "inherit"} onValueChange={(v) => onChange(v === "inherit" ? "" : v)}>
      <SelectTrigger><SelectValue placeholder="Choose a language…" /></SelectTrigger>
      <SelectContent>
        {inheritLabel && <SelectItem value="inherit">{inheritLabel}</SelectItem>}
        {(langs.data?.languages ?? []).map((l) => (
          <SelectItem key={l.value} value={l.value}>{l.label}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** Voice picker: the language's stock voices plus this company's ready cloned
 * voices. Value "" = `emptyLabel` (the language's default voice, or the agent's own). */
export function VoiceSelect({
  language,
  value,
  onChange,
  emptyLabel = "Default voice for this language",
}: {
  language: string;
  value: string;
  onChange: (v: string) => void;
  emptyLabel?: string;
}) {
  const langs = useLanguages();
  const cloned = useClonedVoices();
  const entry = langs.data?.languages.find((l) => l.value === language);
  if (!entry) {
    return <p className="text-xs text-muted-foreground">{langs.isLoading ? "Loading voices…" : "Pick a language first."}</p>;
  }
  const mine = entry.cloned_voices
    ? (cloned.data ?? []).filter((v) => v.status === "ready" && v.voice_id)
    : [];
  return (
    <Select value={value || "default"} onValueChange={(v) => onChange(v === "default" ? "" : v)}>
      <SelectTrigger><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value="default">{emptyLabel}</SelectItem>
        <SelectGroup>
          <SelectLabel>{entry.label} voices</SelectLabel>
          {entry.voices.map((v) => (
            <SelectItem key={v.id} value={v.id}>
              {v.name} <span className="text-muted-foreground">({v.gender})</span>
            </SelectItem>
          ))}
        </SelectGroup>
        {mine.length > 0 && (
          <SelectGroup>
            <SelectLabel>Your cloned voices</SelectLabel>
            {mine.map((v) => (
              <SelectItem key={v.id} value={v.voice_id ?? ""}>{v.name}</SelectItem>
            ))}
          </SelectGroup>
        )}
      </SelectContent>
    </Select>
  );
}
