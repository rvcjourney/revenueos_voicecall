import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/shared/PageHeader";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { ConfirmDialog } from "@/components/platform/ConfirmDialog";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { platformApiErrorMessage } from "@/lib/platformApi";
import { usePlatformEngines, useUpdatePlatformEngines } from "@/lib/platformHooks";
import type { EngineLanguage, EnginesUpdate } from "@/lib/platformTypes";

/** Owner switches for the two calling engines. Every change applies from the
 * next call (<= 60 s), never to a call in progress, and is audit-logged. */
export default function PlatformEngines() {
  const engines = usePlatformEngines();
  const update = useUpdatePlatformEngines();
  const [confirmOff, setConfirmOff] = useState(false);
  const [voicesFor, setVoicesFor] = useState<string | null>(null);

  async function save(data: EnginesUpdate, label: string) {
    try {
      await update.mutateAsync(data);
      toast.success(label);
    } catch (err) {
      toast.error(platformApiErrorMessage(err, "Couldn't update calling engines"));
    }
  }

  if (engines.isError) return <ErrorBanner error={engines.error} onRetry={() => engines.refetch()} />;
  const d = engines.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Calling engines"
        description="Standard (Sarvam STT + Groq Qwen + ElevenLabs/Bulbul) and Indic Native (Sarvam STT + sarvam-105b-conversations + Bulbul). Changes apply to the next call; calls in progress finish unchanged."
      />

      <Card>
        <CardHeader>
          <CardTitle>Indic Native — global switch</CardTitle>
          <CardDescription>
            Incident kill-switch (Sarvam outage, a retired model, a bad release). Off: no new call anywhere starts on
            Indic Native — stock-voice campaigns run on Standard, campaigns using a Sarvam cloned voice pause.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center justify-between pt-0">
          {d ? (
            <p className="text-sm">
              {d.global_enabled ? "On" : "Off"} · enabled for {d.orgs_enabled} organisation{d.orgs_enabled === 1 ? "" : "s"}
            </p>
          ) : <Skeleton className="h-5 w-48" />}
          <Switch
            checked={!!d?.global_enabled}
            disabled={!d || update.isPending}
            onCheckedChange={(v) => (v ? save({ global_enabled: true }, "Indic Native switched on") : setConfirmOff(true))}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Languages</CardTitle>
          <CardDescription>
            Enable each language per engine, and pick Indic Native's voice model per language. Malayalam and Odia stay
            off until they pass an ear-check on real calls.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          {!d ? <Skeleton className="h-64 w-full" /> : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Language</TableHead>
                  <TableHead>Standard</TableHead>
                  <TableHead>Indic Native</TableHead>
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

      <Card>
        <CardHeader>
          <CardTitle>Campaigns paused by an engine switch</CardTitle>
          <CardDescription>These use a Sarvam cloned voice, so they can't fall back to Standard. Resume them once Indic Native is back on.</CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          {!d ? <Skeleton className="h-10 w-full" /> : d.paused_campaigns.length === 0 ? (
            <p className="text-sm text-muted-foreground">None.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {d.paused_campaigns.map((c) => (
                <li key={c.id}>
                  {c.name} · <Link to={`/ops/organizations/${c.org_id}`} className="text-primary hover:underline">{c.org_name}</Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmOff}
        onOpenChange={setConfirmOff}
        title="Switch Indic Native off everywhere?"
        description="New calls stop using it within a minute. Calls already in progress finish normally. Campaigns using a Sarvam cloned voice will pause."
        confirmLabel="Switch off"
        variant="destructive"
        loading={update.isPending}
        onConfirm={async () => {
          await save({ global_enabled: false }, "Indic Native switched off");
          setConfirmOff(false);
        }}
      />
    </div>
  );
}

function Effective({ value }: { value: string }) {
  return <span className={cn("text-xs", value === "on" ? "text-success" : "text-muted-foreground")}>{value}</span>;
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
  const s = lang.sarvam;
  const shortlist = new Set(s.shortlist);
  return (
    <>
      <TableRow>
        <TableCell className="font-medium">{lang.display}</TableCell>
        <TableCell>
          <div className="flex items-center gap-2">
            <Switch checked={lang.standard.enabled} disabled={disabled}
              onCheckedChange={(v) => onChange({ standard: { enabled: v } }, `${lang.display} ${v ? "enabled" : "disabled"} on Standard`)} />
            <Effective value={lang.standard.effective} />
          </div>
        </TableCell>
        <TableCell>
          <div className="flex items-center gap-2">
            <Switch checked={s.enabled} disabled={disabled}
              onCheckedChange={(v) => onChange({ sarvam: { enabled: v } }, `${lang.display} ${v ? "enabled" : "disabled"} on Indic Native`)} />
            <Effective value={s.effective} />
          </div>
        </TableCell>
        <TableCell>
          <Select value={s.tts_model ?? ""} disabled={disabled}
            onValueChange={(v) => onChange({ sarvam: { tts_model: v } }, `${lang.display} voice model: ${v}`)}>
            <SelectTrigger className="h-8 w-36"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="bulbul:v4-flash">bulbul:v4-flash</SelectItem>
              <SelectItem value="bulbul:v3">bulbul:v3</SelectItem>
            </SelectContent>
          </Select>
        </TableCell>
        <TableCell>
          <button type="button" className="text-xs text-primary hover:underline" onClick={onEditVoices}>
            {s.shortlist.length ? `${s.shortlist.length} of ${s.voices.length}` : `all ${s.voices.length}`}
          </button>
        </TableCell>
      </TableRow>
      {editing && (
        <TableRow>
          <TableCell colSpan={5}>
            <p className="mb-2 text-xs text-muted-foreground">
              Voices customers can pick for {lang.display} on Indic Native ({s.tts_model}). None ticked = all.
            </p>
            <div className="flex flex-wrap gap-2">
              {s.voices.map((v) => {
                const on = shortlist.has(v.id);
                return (
                  <button
                    key={v.id}
                    type="button"
                    disabled={disabled}
                    onClick={() => {
                      const next = on ? s.shortlist.filter((x) => x !== v.id) : [...s.shortlist, v.id];
                      onChange({ sarvam: { voices: next } }, `${lang.display} voices updated`);
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
