import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useClonedVoices, useEngines, useLanguages } from "@/lib/hooks";
import { LANGUAGES } from "@/lib/languages";
import type { Pipeline } from "@/lib/types";

/** Form changes when the calling engine changes: a voice picked for one engine
 * never works on the other, so it's cleared rather than failing on save. */
export function engineSwitchPatch(next: Pipeline) {
  return { pipeline: next, voice_id: "", voice_provider: next === "sarvam" ? "sarvam" : "elevenlabs" } as const;
}

/** "Calling engine" picker — renders nothing unless the owner enabled a second
 * engine for this company, so most customers never see it. */
export function EngineSelect({
  value,
  onChange,
  allowInherit,
}: {
  value: Pipeline | null | undefined;
  onChange: (v: Pipeline | null) => void;
  /** Campaigns: allow "Same as the AI agent" (null). */
  allowInherit?: boolean;
}) {
  const engines = useEngines();
  const options = engines.data?.engines ?? [];
  if (options.length < 2) return null;
  return (
    <div className="space-y-1.5">
      <Label>Calling engine</Label>
      <Select value={value ?? "inherit"} onValueChange={(v) => onChange(v === "inherit" ? null : (v as Pipeline))}>
        <SelectTrigger><SelectValue /></SelectTrigger>
        <SelectContent>
          {allowInherit && <SelectItem value="inherit">Same as the AI agent</SelectItem>}
          {options.map((e) => (
            <SelectItem key={e.value} value={e.value}>{e.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/** Languages valid on the chosen engine (from the server registry); falls back
 * to the local list while loading so the form never renders empty. */
export function useEngineLanguages(pipeline: Pipeline) {
  const langs = useLanguages(pipeline);
  return langs.data ?? (pipeline === "standard" ? LANGUAGES.map((l) => ({ ...l, cloned_voices: true })) : []);
}

/** Voice picker for the Indic Native engine: that language's stock voices (all of
 * them, even when there are only two or three) plus this company's ready cloned
 * voices made for this engine. */
export function IndicNativeVoiceSelect({
  language,
  value,
  onChange,
  includeCloned = true,
  placeholder = "Choose a voice…",
}: {
  language: string;
  value: string;
  onChange: (v: string) => void;
  includeCloned?: boolean;
  placeholder?: string;
}) {
  const langs = useLanguages("sarvam");
  const cloned = useClonedVoices();
  const entry = (langs.data ?? []).find((l) => l.value === language);
  const stock = entry?.voices ?? [];
  const mine = includeCloned && entry?.cloned_voices
    ? (cloned.data ?? []).filter((v) => v.engine === "sarvam" && v.status === "ready" && v.elevenlabs_voice_id)
    : [];
  if (!entry) {
    return <p className="text-xs text-muted-foreground">{langs.isLoading ? "Loading voices…" : "Pick a language first."}</p>;
  }
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger><SelectValue placeholder={placeholder} /></SelectTrigger>
      <SelectContent>
        <SelectGroup>
          <SelectLabel>{entry.label} voices</SelectLabel>
          {stock.map((v) => (
            <SelectItem key={v.id} value={v.id}>
              {v.name} <span className="text-muted-foreground">({v.gender})</span>
            </SelectItem>
          ))}
        </SelectGroup>
        {mine.length > 0 && (
          <SelectGroup>
            <SelectLabel>Your cloned voices</SelectLabel>
            {mine.map((v) => (
              <SelectItem key={v.id} value={v.elevenlabs_voice_id ?? ""}>{v.name}</SelectItem>
            ))}
          </SelectGroup>
        )}
      </SelectContent>
    </Select>
  );
}
