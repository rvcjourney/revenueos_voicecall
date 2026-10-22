import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/shared/PageHeader";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { platformApiErrorMessage } from "@/lib/platformApi";
import { usePlatformEngines, usePlatformEnginesLatency, useUpdatePlatformEngines } from "@/lib/platformHooks";
import type { EngineLanguage, EnginesUpdate } from "@/lib/platformTypes";

/** Owner settings for the calling engine (Sarvam STT + sarvam-105b-conversations
 * + Bulbul): which languages are on, each one's voice model and voice shortlist.
 * Every change applies from the next call (<= 60 s) and is audit-logged. */
export default function PlatformEngines() {
  const engines = usePlatformEngines();
  const update = useUpdatePlatformEngines();
  const [voicesFor, setVoicesFor] = useState<string | null>(null);

  async function save(data: EnginesUpdate, label: string) {
    try {
      await update.mutateAsync(data);
      toast.success(label);
    } catch (err) {
      toast.error(platformApiErrorMessage(err, "Couldn't update languages"));
    }
  }

  if (engines.isError) return <ErrorBanner error={engines.error} onRetry={() => engines.refetch()} />;
  const d = engines.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Languages & voices"
        description="Every call runs on Sarvam: realtime STT, sarvam-105b-conversations and Bulbul. Changes apply to the next call; calls in progress finish unchanged."
      />

      <Card>
        <CardHeader>
          <CardTitle>Languages</CardTitle>
          <CardDescription>
            Turn each language on or off and pick its voice model. Malayalam and Odia stay off until they pass an
            ear-check on real calls.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          {!d ? <Skeleton className="h-64 w-full" /> : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Language</TableHead>
                  <TableHead>Enabled</TableHead>
                  <TableHead>Voice model</TableHead>
                  <TableHead>Voices</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {d.languages.map((l) => (
                  <LanguageRow
                    key={l.key}
                    lang={l}
                    disabled={update.isPending}
                    onChange={(patch, label) => save({ languages: { [l.key]: patch } }, label)}
                    onEditVoices={() => setVoicesFor(voicesFor === l.key ? null : l.key)}
                    editing={voicesFor === l.key}
                  />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <LatencyCard />
    </div>
  );
}

function ms(v: number | null | undefined) {
  return v == null ? "—" : `${Math.round(v * 1000)} ms`;
}

function LatencyCard() {
  const latency = usePlatformEnginesLatency(7);
  const rows = latency.data ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Latency — last 7 days</CardTitle>
        <CardDescription>
          From each call's per-turn LiveKit metrics. Sarvam's guidance for this stack: reply latency p50 under 900 ms is
          good, under 1.4 s acceptable; p95 under 1.8 s good. "Old engine" rows are calls from before the Sarvam-only change.
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        {latency.isLoading ? <Skeleton className="h-24 w-full" /> : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No calls with latency data yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Engine</TableHead>
                <TableHead>Calls</TableHead>
                <TableHead>Reply p50 / p95</TableHead>
                <TableHead>STT delay p95</TableHead>
                <TableHead>LLM first token p50</TableHead>
                <TableHead>TTS first byte p95</TableHead>
                <TableHead>False interruptions</TableHead>
                <TableHead>Empty replies</TableHead>
                <TableHead>Clone fallbacks</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.engine}>
                  <TableCell className="font-medium">{r.engine === "sarvam" ? "Sarvam" : "Old engine"}</TableCell>
                  <TableCell>{r.calls}</TableCell>
                  <TableCell>{ms(r.metrics.e2e_latency?.p50)} / {ms(r.metrics.e2e_latency?.p95)}</TableCell>
                  <TableCell>{ms(r.metrics.transcription_delay?.p95)}</TableCell>
                  <TableCell>{ms(r.metrics.llm_node_ttft?.p50)}</TableCell>
                  <TableCell>{ms(r.metrics.tts_node_ttfb?.p95)}</TableCell>
                  <TableCell>{r.false_interruption_rate == null ? "—" : `${(r.false_interruption_rate * 100).toFixed(1)}%`}</TableCell>
                  <TableCell>{r.counts.empty_replies ?? 0}</TableCell>
                  <TableCell>{r.counts.clone_fallback ?? 0}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function LanguageRow({
  lang,
  disabled,
  onChange,
  onEditVoices,
  editing,
}: {
  lang: EngineLanguage;
  disabled: boolean;
  onChange: (patch: NonNullable<EnginesUpdate["languages"]>[string], label: string) => void;
  onEditVoices: () => void;
  editing: boolean;
}) {
  const shortlist = new Set(lang.shortlist);
  return (
    <>
      <TableRow>
        <TableCell className="font-medium">{lang.display}</TableCell>
        <TableCell>
          <Switch checked={lang.enabled} disabled={disabled}
            onCheckedChange={(v) => onChange({ enabled: v }, `${lang.display} ${v ? "enabled" : "disabled"}`)} />
        </TableCell>
        <TableCell>
          <Select value={lang.tts_model} disabled={disabled}
            onValueChange={(v) => onChange({ tts_model: v }, `${lang.display} voice model: ${v}`)}>
            <SelectTrigger className="h-8 w-36"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="bulbul:v4-flash">bulbul:v4-flash</SelectItem>
              <SelectItem value="bulbul:v3">bulbul:v3</SelectItem>
            </SelectContent>
          </Select>
        </TableCell>
        <TableCell>
          <button type="button" className="text-xs text-primary hover:underline" onClick={onEditVoices}>
            {lang.shortlist.length ? `${lang.shortlist.length} of ${lang.voices.length}` : `all ${lang.voices.length}`}
          </button>
        </TableCell>
      </TableRow>
      {editing && (
        <TableRow>
          <TableCell colSpan={4}>
            <p className="mb-2 text-xs text-muted-foreground">
              Voices customers can pick for {lang.display} ({lang.tts_model}). None ticked = all.
            </p>
            <div className="flex flex-wrap gap-2">
              {lang.voices.map((v) => {
                const on = shortlist.has(v.id);
                return (
                  <button
                    key={v.id}
                    type="button"
                    disabled={disabled}
                    onClick={() => {
                      const next = on ? lang.shortlist.filter((x) => x !== v.id) : [...lang.shortlist, v.id];
                      onChange({ voices: next }, `${lang.display} voices updated`);
                    }}
                    className={cn("rounded-full border px-2.5 py-1 text-xs", on ? "border-primary bg-primary/10" : "border-border")}
                  >
                    {v.name} ({v.gender}) <span className="text-muted-foreground">{v.id}</span>
                  </button>
                );
              })}
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}
