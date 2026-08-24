import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Bot, Download, FileText, ListTree, Loader2, MessageSquare, RefreshCw, User } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { EmptyState } from "@/components/shared/EmptyState";
import { CallOutcomeBadge, CallStatusBadge, SentimentBadge } from "@/components/shared/StatusBadge";
import { useCall, useFetchRecording } from "@/lib/hooks";
import { api, apiErrorMessage } from "@/lib/api";
import { callDurationSeconds, cn, formatDateTime, formatDuration, titleCase } from "@/lib/utils";

export default function CallDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const call = useCall(id);
  const fetchRecording = useFetchRecording();
  const [recordingBlobUrl, setRecordingBlobUrl] = useState<string | null>(null);
  const [recordingError, setRecordingError] = useState(false);

  // <audio src>/<a href> can't carry the app's Authorization header, and the
  // recording proxy endpoint requires one — fetch it as an authenticated
  // blob instead and point playback/download at the resulting object URL.
  useEffect(() => {
    const recordingUrl = call.data?.recording_url;
    const callId = call.data?.id;
    if (!recordingUrl || !callId) {
      setRecordingBlobUrl(null);
      return;
    }
    let objectUrl: string | null = null;
    let cancelled = false;
    setRecordingError(false);
    api
      .get(`/api/calls/${callId}/recording`, { responseType: "blob" })
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        setRecordingBlobUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setRecordingError(true);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [call.data?.id, call.data?.recording_url]);

  if (call.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (call.isError || !call.data) {
    return <ErrorBanner error={call.error} onRetry={() => call.refetch()} />;
  }

  const c = call.data;
  const defaultTab = c.summary ? "summary" : "transcript";

  // Reached from several places (global call history, a campaign's Calls tab,
  // the dashboard's recent-calls card) -- a hardcoded `Link to="/calls"` here
  // sent every one of them back to call history regardless of where they
  // actually came from. True back-navigation fixes all of them at once.
  // location.key is "default" only when there's no real SPA history to go
  // back to (e.g. this page was loaded directly / refreshed) -- fall back to
  // call history in that case instead of navigating out of the app.
  function handleBack() {
    if (location.key !== "default") navigate(-1);
    else navigate("/calls");
  }

  async function handleFetchRecording() {
    if (!id) return;
    try {
      const res = await fetchRecording.mutateAsync(id);
      if (res.data.found) {
        toast.success("Recording found");
      } else {
        toast.info("Recording isn't available yet — it may still be processing.");
      }
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't fetch recording"));
    }
  }

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" onClick={handleBack} className="-ml-2">
        <ArrowLeft className="h-4 w-4" /> Back
      </Button>

      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-heading text-2xl font-semibold sm:text-3xl">{c.phone_number}</h1>
            <CallOutcomeBadge outcome={c.outcome} status={c.status} />
            <CallStatusBadge status={c.status} />
            {c.sentiment && <SentimentBadge sentiment={c.sentiment} />}
          </div>
          <p className="text-sm text-muted-foreground">
            {formatDateTime(c.started_at)} · {formatDuration(callDurationSeconds(c))}
            {c.cost_inr != null && ` · ₹${c.cost_inr.toFixed(2)}`}
          </p>
        </div>
      </div>

      {c.error_message && <ErrorBanner error={new Error(c.error_message)} />}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card>
            <CardContent className="pt-6">
              <Tabs defaultValue={defaultTab}>
                <TabsList>
                  <TabsTrigger value="summary" disabled={!c.summary}>
                    <MessageSquare className="h-3.5 w-3.5" /> Summary
                  </TabsTrigger>
                  <TabsTrigger value="transcript">
                    <FileText className="h-3.5 w-3.5" /> Transcript
                  </TabsTrigger>
                  <TabsTrigger value="extracted">
                    <ListTree className="h-3.5 w-3.5" /> Extracted data
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="summary">
                  {c.summary ? (
                    <p className="text-sm leading-relaxed text-foreground/90">{c.summary}</p>
                  ) : (
                    <EmptyState title="No summary available" description="An AI summary will appear here once the call is processed." />
                  )}
                </TabsContent>

                <TabsContent value="transcript" className="space-y-3">
                  {c.transcript_segments.length > 0 ? (
                    c.transcript_segments.map((seg, i) => {
                      const isAgent = seg.speaker.toLowerCase().includes("agent") || seg.speaker.toLowerCase().includes("ai");
                      const timestamp = seg.start_ms != null ? formatDuration(Math.floor(seg.start_ms / 1000)) : null;
                      return (
                        <div key={i} className={cn("flex gap-2", isAgent ? "" : "flex-row-reverse")}>
                          <span
                            className={cn(
                              "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
                              isAgent ? "bg-primary/15 text-primary" : "bg-secondary text-secondary-foreground"
                            )}
                          >
                            {isAgent ? <Bot className="h-3.5 w-3.5" /> : <User className="h-3.5 w-3.5" />}
                          </span>
                          <div className={cn("max-w-[80%] rounded-xl px-3 py-2 text-sm", isAgent ? "rounded-tl-sm bg-muted" : "rounded-tr-sm bg-primary/15")}>
                            <p className="mb-0.5 flex items-center gap-2 text-xs font-medium text-muted-foreground">
                              {titleCase(seg.speaker)}
                              {timestamp && <span className="font-normal tabular-figure text-muted-foreground/70">{timestamp}</span>}
                            </p>
                            {seg.text}
                          </div>
                        </div>
                      );
                    })
                  ) : c.transcript_full_text ? (
                    <p className="whitespace-pre-wrap text-sm text-muted-foreground">{c.transcript_full_text}</p>
                  ) : (
                    <EmptyState title="No transcript available" description="A transcript will appear here once this call is processed." />
                  )}
                </TabsContent>

                <TabsContent value="extracted">
                  {Object.keys(c.extracted_data ?? {}).length > 0 ? (
                    <dl className="space-y-2 text-sm">
                      {Object.entries(c.extracted_data).map(([key, value]) => (
                        <div key={key} className="flex justify-between gap-3 border-b border-border/60 pb-2 last:border-0">
                          <dt className="capitalize text-muted-foreground">{key.replace(/_/g, " ")}</dt>
                          <dd className="text-right font-medium">{String(value)}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : (
                    <EmptyState title="No structured data" description="Fields extracted from this call will appear here." />
                  )}
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader><CardTitle>Recording</CardTitle></CardHeader>
            <CardContent className="space-y-3 pt-0">
              {c.recording_url ? (
                recordingBlobUrl ? (
                  <>
                    <audio controls className="w-full" src={recordingBlobUrl} />
                    <Button variant="outline" size="sm" className="w-full" asChild>
                      <a href={recordingBlobUrl} download={`call_${c.id}.mp3`}>
                        <Download className="h-3.5 w-3.5" /> Download
                      </a>
                    </Button>
                  </>
                ) : recordingError ? (
                  <p className="text-center text-sm text-destructive">Couldn't load the recording.</p>
                ) : (
                  <div className="flex justify-center py-4">
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                  </div>
                )
              ) : (
                <div className="space-y-2 text-center">
                  <p className="text-sm text-muted-foreground">No recording yet — it can take a few minutes to arrive.</p>
                  <Button variant="outline" size="sm" onClick={handleFetchRecording} disabled={fetchRecording.isPending}>
                    {fetchRecording.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                    Fetch recording
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
