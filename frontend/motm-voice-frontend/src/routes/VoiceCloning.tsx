import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Loader2, Mic, Play, RotateCcw, Square, Trash2, Upload, Video, Volume2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { useClonedVoices, useCreateClonedVoice, useDeleteClonedVoice } from "@/lib/hooks";
import { apiErrorMessage } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { VOICE_CLONING_CONSENT_SCRIPT } from "@/lib/consentScript";

function formatElapsed(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const STATUS_VARIANTS: Record<string, "success" | "warning" | "destructive"> = {
  ready: "success",
  pending: "warning",
  rejected: "destructive",
  failed: "destructive",
};

const STATUS_LABELS: Record<string, string> = {
  ready: "Ready",
  pending: "Pending review",
  rejected: "Rejected",
  failed: "Failed",
};

// Must match MAX_CLONED_VOICES_PER_ORG in backend/app/core/plan_features.py --
// a flat platform-wide cap, not plan-based. Rejected requests never occupy a
// slot (they never became, and never will become, a real voice).
const MAX_CLONED_VOICES_PER_ORG = 2;

export default function VoiceCloning() {
  const clonedVoices = useClonedVoices();
  const createVoice = useCreateClonedVoice();
  const deleteVoice = useDeleteClonedVoice();

  const [name, setName] = useState("");

  const slotsUsed = clonedVoices.data?.filter((v) => v.status === "ready" || v.status === "pending").length ?? 0;
  const atCap = slotsUsed >= MAX_CLONED_VOICES_PER_ORG;

  // ── Audio sample (upload or record) ─────────────────────────────────────
  const [source, setSource] = useState<"upload" | "record">("upload");
  const [file, setFile] = useState<File | null>(null);
  const [recording, setRecording] = useState(false);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [recordedUrl, setRecordedUrl] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const recordedUrlRef = useRef<string | null>(null);
  recordedUrlRef.current = recordedUrl;

  // ── Consent video (upload or record) ────────────────────────────────────
  const [videoSource, setVideoSource] = useState<"upload" | "record">("record");
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoRecording, setVideoRecording] = useState(false);
  const [recordedVideoBlob, setRecordedVideoBlob] = useState<Blob | null>(null);
  const [recordedVideoUrl, setRecordedVideoUrl] = useState<string | null>(null);
  const [videoElapsed, setVideoElapsed] = useState(0);
  const videoRecorderRef = useRef<MediaRecorder | null>(null);
  const videoChunksRef = useRef<Blob[]>([]);
  const videoTimerRef = useRef<number | null>(null);
  const recordedVideoUrlRef = useRef<string | null>(null);
  recordedVideoUrlRef.current = recordedVideoUrl;
  const videoPreviewRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
      if (recordedUrlRef.current) URL.revokeObjectURL(recordedUrlRef.current);
      mediaRecorderRef.current?.stream.getTracks().forEach((t) => t.stop());

      if (videoTimerRef.current) window.clearInterval(videoTimerRef.current);
      if (recordedVideoUrlRef.current) URL.revokeObjectURL(recordedVideoUrlRef.current);
      videoRecorderRef.current?.stream.getTracks().forEach((t) => t.stop());
    };
  }, []);

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        setRecordedBlob(blob);
        setRecordedUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return URL.createObjectURL(blob);
        });
        stream.getTracks().forEach((t) => t.stop());
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setRecording(true);
      setElapsed(0);
      timerRef.current = window.setInterval(() => setElapsed((e) => e + 1), 1000);
    } catch {
      toast.error("Couldn't access your microphone — check browser permissions");
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
    setRecording(false);
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  function resetSource() {
    setFile(null);
    setRecordedBlob(null);
    if (recordedUrl) URL.revokeObjectURL(recordedUrl);
    setRecordedUrl(null);
    setElapsed(0);
  }

  async function startVideoRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      if (videoPreviewRef.current) {
        videoPreviewRef.current.srcObject = stream;
      }
      const recorder = new MediaRecorder(stream);
      videoChunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) videoChunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(videoChunksRef.current, { type: recorder.mimeType || "video/webm" });
        setRecordedVideoBlob(blob);
        setRecordedVideoUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return URL.createObjectURL(blob);
        });
        stream.getTracks().forEach((t) => t.stop());
        if (videoPreviewRef.current) videoPreviewRef.current.srcObject = null;
      };
      recorder.start();
      videoRecorderRef.current = recorder;
      setVideoRecording(true);
      setVideoElapsed(0);
      videoTimerRef.current = window.setInterval(() => setVideoElapsed((e) => e + 1), 1000);
    } catch {
      toast.error("Couldn't access your camera — check browser permissions");
    }
  }

  function stopVideoRecording() {
    videoRecorderRef.current?.stop();
    setVideoRecording(false);
    if (videoTimerRef.current) {
      window.clearInterval(videoTimerRef.current);
      videoTimerRef.current = null;
    }
  }

  function resetVideoSource() {
    setVideoFile(null);
    setRecordedVideoBlob(null);
    if (recordedVideoUrl) URL.revokeObjectURL(recordedVideoUrl);
    setRecordedVideoUrl(null);
    setVideoElapsed(0);
  }

  async function handleCreate() {
    if (atCap) {
      toast.error(
        `Maximum limit for cloned voices is ${MAX_CLONED_VOICES_PER_ORG}. Delete one of your existing voices, then try cloning again.`
      );
      return;
    }
    if (!name.trim()) {
      toast.error("Give your cloned voice a name");
      return;
    }
    const audioFile =
      source === "upload"
        ? file
        : recordedBlob
        ? new File([recordedBlob], `${name.trim().replace(/\s+/g, "-").toLowerCase()}.webm`, {
            type: recordedBlob.type || "audio/webm",
          })
        : null;

    if (!audioFile) {
      toast.error(source === "upload" ? "Choose an audio sample to upload" : "Record a voice sample first");
      return;
    }

    const consentVideoFile =
      videoSource === "upload"
        ? videoFile
        : recordedVideoBlob
        ? new File(
            [recordedVideoBlob],
            `${name.trim().replace(/\s+/g, "-").toLowerCase()}-consent.webm`,
            { type: recordedVideoBlob.type || "video/webm" }
          )
        : null;

    if (!consentVideoFile) {
      toast.error(videoSource === "upload" ? "Upload your consent video" : "Record your consent video first");
      return;
    }

    try {
      await createVoice.mutateAsync({ name: name.trim(), file: audioFile, consentVideo: consentVideoFile });
      toast.success("Submitted for review — you'll see it here once approved");
      setName("");
      resetSource();
      resetVideoSource();
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't submit voice cloning request"));
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this cloned voice? Agents using it will need a new voice assigned.")) return;
    try {
      await deleteVoice.mutateAsync(id);
      toast.success("Deleted");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't delete"));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Voice Cloning"
        description="Create reusable cloned voices, then pick them for any AI agent."
      />

      <Card>
        <CardContent className="space-y-4 pt-6">
          <div>
            <p className="font-medium">
              Create a cloned voice
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                ({slotsUsed}/{MAX_CLONED_VOICES_PER_ORG} used)
              </span>
            </p>
            <p className="text-sm text-muted-foreground">
              Name it, provide a voice sample, and record a short consent video — every submission is reviewed
              before the voice becomes usable.
            </p>
          </div>

          {atCap && (
            <div className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2.5 text-sm text-warning">
              Maximum limit for cloned voices is {MAX_CLONED_VOICES_PER_ORG} (pending requests count too). Delete
              one of your existing voices below, then try cloning again.
            </div>
          )}

          <div className="max-w-sm space-y-1.5">
            <Label>Voice name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Priya" />
          </div>

          <Tabs
            value={source}
            onValueChange={(v) => {
              setSource(v as "upload" | "record");
              resetSource();
            }}
          >
            <TabsList>
              <TabsTrigger value="upload" className="gap-1.5">
                <Upload className="h-3.5 w-3.5" /> Upload audio
              </TabsTrigger>
              <TabsTrigger value="record" className="gap-1.5">
                <Mic className="h-3.5 w-3.5" /> Record audio
              </TabsTrigger>
            </TabsList>

            <TabsContent value="upload" className="max-w-sm space-y-1.5">
              <Label>Sample audio</Label>
              <Input type="file" accept="audio/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </TabsContent>

            <TabsContent value="record" className="space-y-3">
              <div className="flex items-center gap-3 rounded-lg border border-border p-3">
                {!recording ? (
                  <Button type="button" variant="outline" size="sm" onClick={startRecording}>
                    <Mic className="h-3.5 w-3.5" /> Start recording
                  </Button>
                ) : (
                  <Button type="button" variant="destructive" size="sm" onClick={stopRecording}>
                    <Square className="h-3.5 w-3.5" /> Stop
                  </Button>
                )}
                <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                  {recording && <span className="h-2 w-2 rounded-full bg-destructive animate-pulse-glow" />}
                  {formatElapsed(elapsed)}
                </span>
                {recordedUrl && !recording && (
                  <span className="flex items-center gap-1.5 text-xs text-success">
                    <Play className="h-3 w-3" /> Sample ready
                  </span>
                )}
                {recordedUrl && !recording && (
                  <Button type="button" variant="ghost" size="sm" onClick={resetSource}>
                    <RotateCcw className="h-3.5 w-3.5" /> Retake
                  </Button>
                )}
              </div>
              {recordedUrl && (
                <audio src={recordedUrl} controls className="h-9 w-full max-w-sm" />
              )}
            </TabsContent>
          </Tabs>

          <div className="space-y-3 rounded-xl border border-border/60 bg-muted/20 p-4">
            <div>
              <p className="font-medium">Consent video</p>
              <p className="text-sm text-muted-foreground">
                Read the script below on camera — this is kept as proof of consent and reviewed before approval.
              </p>
            </div>
            <p className="rounded-lg border border-dashed border-border bg-card px-3 py-2 text-sm italic text-foreground/90">
              &ldquo;{VOICE_CLONING_CONSENT_SCRIPT}&rdquo;
            </p>

            <Tabs
              value={videoSource}
              onValueChange={(v) => {
                setVideoSource(v as "upload" | "record");
                resetVideoSource();
              }}
            >
              <TabsList>
                <TabsTrigger value="record" className="gap-1.5">
                  <Video className="h-3.5 w-3.5" /> Record video
                </TabsTrigger>
                <TabsTrigger value="upload" className="gap-1.5">
                  <Upload className="h-3.5 w-3.5" /> Upload video
                </TabsTrigger>
              </TabsList>

              <TabsContent value="upload" className="max-w-sm space-y-1.5">
                <Label>Consent video file</Label>
                <Input type="file" accept="video/*" onChange={(e) => setVideoFile(e.target.files?.[0] ?? null)} />
              </TabsContent>

              <TabsContent value="record" className="space-y-3">
                <div className="flex items-center gap-3 rounded-lg border border-border p-3">
                  {!videoRecording ? (
                    <Button type="button" variant="outline" size="sm" onClick={startVideoRecording}>
                      <Video className="h-3.5 w-3.5" /> Start recording
                    </Button>
                  ) : (
                    <Button type="button" variant="destructive" size="sm" onClick={stopVideoRecording}>
                      <Square className="h-3.5 w-3.5" /> Stop
                    </Button>
                  )}
                  <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                    {videoRecording && <span className="h-2 w-2 rounded-full bg-destructive animate-pulse-glow" />}
                    {formatElapsed(videoElapsed)}
                  </span>
                  {recordedVideoUrl && !videoRecording && (
                    <span className="flex items-center gap-1.5 text-xs text-success">
                      <Play className="h-3 w-3" /> Video ready
                    </span>
                  )}
                  {recordedVideoUrl && !videoRecording && (
                    <Button type="button" variant="ghost" size="sm" onClick={resetVideoSource}>
                      <RotateCcw className="h-3.5 w-3.5" /> Retake
                    </Button>
                  )}
                </div>
                {/* Always mounted (not conditional on videoRecording) so videoPreviewRef
                    is already attached by the time startVideoRecording() assigns
                    srcObject -- otherwise that assignment lands on a still-null ref,
                    since the state update that would mount it hasn't re-rendered yet. */}
                <video
                  ref={videoPreviewRef}
                  autoPlay
                  muted
                  playsInline
                  className={`max-w-sm rounded-lg border border-border ${videoRecording ? "" : "hidden"}`}
                />
                {recordedVideoUrl && !videoRecording && (
                  <video src={recordedVideoUrl} controls className="max-w-sm rounded-lg border border-border" />
                )}
              </TabsContent>
            </Tabs>
          </div>

          <Button type="button" variant="gradient" onClick={handleCreate} disabled={createVoice.isPending || atCap}>
            {createVoice.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Volume2 className="h-4 w-4" />}
            Submit for review
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <p className="mb-4 font-medium">Your cloned voices</p>
          {clonedVoices.isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : clonedVoices.data && clonedVoices.data.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {clonedVoices.data.map((v) => (
                  <TableRow key={v.id}>
                    <TableCell className="font-medium">{v.name}</TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        <Badge variant={STATUS_VARIANTS[v.status] ?? "destructive"}>
                          {STATUS_LABELS[v.status] ?? v.status}
                        </Badge>
                        {v.status === "rejected" && v.rejection_reason && (
                          <p className="text-xs text-muted-foreground">Reason: {v.rejection_reason}</p>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{formatDate(v.created_at)}</TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" onClick={() => handleDelete(v.id)} disabled={deleteVoice.isPending}>
                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <EmptyState icon={Mic} title="No cloned voices yet" description="Create one above to reuse it across your AI agents." />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
