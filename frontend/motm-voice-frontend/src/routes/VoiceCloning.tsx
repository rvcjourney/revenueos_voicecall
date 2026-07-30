import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Loader2, Mic, Play, Square, Trash2, Upload, Volume2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
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

function formatElapsed(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function VoiceCloning() {
  const clonedVoices = useClonedVoices();
  const createVoice = useCreateClonedVoice();
  const deleteVoice = useDeleteClonedVoice();

  const [name, setName] = useState("");
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

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
      if (recordedUrlRef.current) URL.revokeObjectURL(recordedUrlRef.current);
      mediaRecorderRef.current?.stream.getTracks().forEach((t) => t.stop());
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

  async function handleCreate() {
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

    try {
      await createVoice.mutateAsync({ name: name.trim(), file: audioFile });
      toast.success("Voice cloning started");
      setName("");
      resetSource();
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't clone voice"));
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this cloned voice? Agents using it will need a new voice assigned.")) return;
    try {
      await deleteVoice.mutateAsync(id);
      toast.success("Cloned voice deleted");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't delete cloned voice"));
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
            <p className="font-medium">Create a cloned voice</p>
            <p className="text-sm text-muted-foreground">Name it, then upload a sample or record one right here.</p>
          </div>

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
              </div>
              {recordedUrl && (
                <audio src={recordedUrl} controls className="h-9 w-full max-w-sm" />
              )}
            </TabsContent>
          </Tabs>

          <Button type="button" variant="gradient" onClick={handleCreate} disabled={createVoice.isPending}>
            {createVoice.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Volume2 className="h-4 w-4" />}
            Clone voice
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
                      <span
                        className={
                          v.status === "ready"
                            ? "inline-flex rounded-full bg-success/15 px-2.5 py-0.5 text-xs font-medium text-success"
                            : "inline-flex rounded-full bg-destructive/15 px-2.5 py-0.5 text-xs font-medium text-destructive"
                        }
                      >
                        {v.status === "ready" ? "Ready" : "Failed"}
                      </span>
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
