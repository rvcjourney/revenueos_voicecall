import { createFileRoute, Link, useParams } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { OutcomeBadge } from "@/components/layout/StatusBadge";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Download, FileText, Loader2, Mic, MicOff } from "lucide-react";
import { api } from "@/lib/api";
import { useCall } from "@/lib/hooks";

export const Route = createFileRoute("/_authed/calls/$id")({
  head: () => ({ meta: [{ title: "Call Detail — MOTMVoice" }] }),
  component: CallDetail,
});

function useRecordingBlob(callId: string, hasRecording: boolean) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const urlRef = useRef<string | null>(null);

  useEffect(() => {
    if (!hasRecording) return;
    let cancelled = false;
    setLoading(true);
    api.get(`/api/calls/${callId}/recording`, { responseType: "blob" })
      .then((res) => {
        if (cancelled) return;
        const url = URL.createObjectURL(res.data);
        urlRef.current = url;
        setBlobUrl(url);
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => {
      cancelled = true;
      if (urlRef.current) { URL.revokeObjectURL(urlRef.current); urlRef.current = null; }
    };
  }, [callId, hasRecording]);

  return { blobUrl, loading };
}

function fmtDur(s: number | null | undefined) {
  if (!s) return "—";
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}m ${String(r).padStart(2, "0")}s`;
}

function CallDetail() {
  const { id } = useParams({ from: "/_authed/calls/$id" });
  const { data, isLoading, isError } = useCall(id);
  // Must be called before any early returns — Rules of Hooks
  const { blobUrl, loading: recordingLoading } = useRecordingBlob(id, !!data?.recording_url);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-center py-32 text-muted-foreground text-sm">
        Call not found.{" "}
        <Link to="/calls" className="underline">Back to calls</Link>
      </div>
    );
  }

  const c = data;
  const segments = c.transcript_segments ?? [];

  return (
    <div className="space-y-6 max-w-7xl">
      <Link to="/calls" className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
        <ArrowLeft className="h-3 w-3" /> Back to calls
      </Link>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Left column: recording + transcript */}
        <div className="space-y-4">

          {/* Audio player */}
          <div className="rounded-xl bg-card border border-border p-5">
            <h3 className="font-semibold mb-4">Recording</h3>
            {c.recording_url ? (
              <div className="space-y-3">
                {recordingLoading ? (
                  <div className="flex items-center justify-center h-16 gap-2 text-muted-foreground text-sm">
                    <Loader2 className="h-4 w-4 animate-spin" /> Loading recording…
                  </div>
                ) : blobUrl ? (
                  <>
                    <audio controls className="w-full rounded-lg" src={blobUrl} preload="metadata">
                      Your browser does not support audio playback.
                    </audio>
                    <div className="flex justify-end">
                      <a href={blobUrl} download={`call_${c.id}.wav`}>
                        <Button variant="outline" size="sm">
                          <Download className="h-3 w-3" /> Download WAV
                        </Button>
                      </a>
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground text-center py-4">
                    Could not load recording.
                  </p>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-28 gap-2 text-muted-foreground">
                <MicOff className="h-8 w-8 opacity-40" />
                <p className="text-sm">
                  {c.status === "completed"
                    ? "Recording not yet available — check back in a minute"
                    : "No recording for this call"}
                </p>
              </div>
            )}
          </div>

          {/* Transcript */}
          <div className="rounded-xl bg-card border border-border p-5">
            <h3 className="font-semibold mb-3 flex items-center gap-2">
              <Mic className="h-4 w-4" /> Transcript
            </h3>
            {segments.length > 0 ? (
              <div className="space-y-2 max-h-[520px] overflow-y-auto pr-1">
                {segments.map((seg, i) => (
                  <div
                    key={i}
                    className={`rounded-lg p-3 ${
                      seg.speaker === "agent"
                        ? "bg-primary/10 border border-primary/20"
                        : "bg-surface-2"
                    }`}
                  >
                    <div className="text-xs font-semibold mb-1 text-muted-foreground">
                      {seg.speaker === "agent" ? "Aniket (AI)" : "Customer"}
                    </div>
                    <div className="text-sm leading-relaxed">{seg.text}</div>
                  </div>
                ))}
              </div>
            ) : c.transcript_full_text ? (
              <pre className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed max-h-96 overflow-y-auto">
                {c.transcript_full_text}
              </pre>
            ) : (
              <div className="flex flex-col items-center justify-center h-28 gap-2 text-muted-foreground">
                <FileText className="h-8 w-8 opacity-40" />
                <p className="text-sm">
                  {c.status === "completed"
                    ? "Transcript is being generated…"
                    : "No transcript available"}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Right column: outcome, summary, metadata */}
        <div className="space-y-4">

          {/* Contact + outcome */}
          <div className="rounded-xl bg-card border border-border p-5">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Phone</div>
                <div className="text-xl font-semibold font-mono">{c.phone_number}</div>
                <div className="text-xs text-muted-foreground mt-1 capitalize">{c.direction} call</div>
              </div>
              <OutcomeBadge outcome={c.outcome} />
            </div>
          </div>

          {/* AI Summary */}
          <div className="rounded-xl bg-card border border-border p-5">
            <h3 className="font-semibold flex items-center gap-2 mb-3">
              <FileText className="h-4 w-4" /> AI Summary
            </h3>
            {c.summary ? (
              <p className="text-sm text-muted-foreground leading-relaxed">{c.summary}</p>
            ) : (
              <p className="text-sm text-muted-foreground italic">
                {c.status === "completed"
                  ? "Summary pending — will be generated after the call is processed."
                  : "No summary available."}
              </p>
            )}
            {c.sentiment && (
              <div className="mt-3 flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Sentiment:</span>
                <span className={`text-xs font-medium capitalize ${
                  c.sentiment === "positive" ? "text-success" :
                  c.sentiment === "negative" ? "text-destructive" :
                  "text-muted-foreground"
                }`}>{c.sentiment}</span>
              </div>
            )}
          </div>

          {/* Call metadata */}
          <div className="rounded-xl bg-card border border-border p-5">
            <h3 className="font-semibold mb-3">Call Details</h3>
            <dl className="text-sm space-y-2">
              {([
                ["Call ID",  c.id],
                ["Status",   c.status],
                ["Started",  c.started_at ? new Date(c.started_at).toLocaleString() : "—"],
                ["Ended",    c.ended_at   ? new Date(c.ended_at).toLocaleString()   : "—"],
                ["Duration", fmtDur(c.duration_seconds)],
                ["Cost",     c.cost_inr != null ? `₹${c.cost_inr.toFixed(2)}` : "—"],
              ] as [string, string][]).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4">
                  <dt className="text-muted-foreground text-xs shrink-0">{k}</dt>
                  <dd className="font-mono text-xs text-right break-all">{v}</dd>
                </div>
              ))}
            </dl>
          </div>

          {/* Extracted data (if any interesting keys) */}
          {c.extracted_data && Object.keys(c.extracted_data).length > 0 && (
            <div className="rounded-xl bg-card border border-border p-5">
              <h3 className="font-semibold mb-3">Extracted Data</h3>
              <dl className="text-sm space-y-2">
                {Object.entries(c.extracted_data).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4">
                    <dt className="text-muted-foreground text-xs capitalize">{k.replace(/_/g, " ")}</dt>
                    <dd className="text-xs text-right">{String(v)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          {c.error_message && (
            <div className="rounded-xl bg-destructive/10 border border-destructive/30 p-4">
              <p className="text-xs text-destructive font-mono">{c.error_message}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
