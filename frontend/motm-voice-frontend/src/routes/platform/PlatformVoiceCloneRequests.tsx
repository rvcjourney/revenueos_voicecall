import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, Mic, X } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { ConfirmDialog } from "@/components/platform/ConfirmDialog";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useApprovePlatformVoiceCloneRequest,
  usePlatformVoiceCloneRequests,
  useRejectPlatformVoiceCloneRequest,
} from "@/lib/platformHooks";
import { platformApi, platformApiErrorMessage } from "@/lib/platformApi";
import { formatDate } from "@/lib/utils";
import { VOICE_CLONING_CONSENT_SCRIPT } from "@/lib/consentScript";
import type { PlatformVoiceCloneRequest } from "@/lib/platformTypes";

const STATUS_FILTERS = [
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
] as const;

export default function PlatformVoiceCloneRequests() {
  const [status, setStatus] = useState<string>("pending");
  const requests = usePlatformVoiceCloneRequests({ status });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Voice Clone Requests"
        description="Review consent videos before a submitted voice becomes usable."
      />

      <div className="flex flex-wrap gap-2">
        {STATUS_FILTERS.map((f) => (
          <Button
            key={f.value}
            size="sm"
            variant={status === f.value ? "gradient" : "outline"}
            onClick={() => setStatus(f.value)}
          >
            {f.label}
          </Button>
        ))}
      </div>

      {requests.isError ? (
        <ErrorBanner error={requests.error} onRetry={() => requests.refetch()} />
      ) : requests.isLoading ? (
        <div className="space-y-4">{[1, 2].map((i) => <Skeleton key={i} className="h-64 w-full" />)}</div>
      ) : requests.data && requests.data.length > 0 ? (
        <div className="space-y-4">
          {requests.data.map((r) => (
            <RequestCard key={r.id} request={r} />
          ))}
        </div>
      ) : (
        <EmptyState icon={Mic} title="Nothing here" description="No voice clone requests match this filter." />
      )}
    </div>
  );
}

// <video>/<audio> src loads can't carry an Authorization header, and these
// files live behind an authenticated proxy endpoint (MinIO itself is
// internal-only — see backend/app/api/platform.py's voice-clone-requests
// audio/video routes) — so fetch the bytes ourselves and hand the player
// a blob: URL instead of the API path directly.
function useAuthedMediaUrl(path: string): string | undefined {
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    let objectUrl: string | undefined;
    let cancelled = false;
    platformApi
      .get(path, { responseType: "blob" })
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        setUrl(objectUrl);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);
  return url;
}

const STATUS_VARIANT: Record<string, "warning" | "success" | "destructive"> = {
  pending: "warning",
  approved: "success",
  rejected: "destructive",
};

function RequestCard({ request }: { request: PlatformVoiceCloneRequest }) {
  const approve = useApprovePlatformVoiceCloneRequest();
  const reject = useRejectPlatformVoiceCloneRequest();
  const [approveConfirmOpen, setApproveConfirmOpen] = useState(false);
  const [rejectConfirmOpen, setRejectConfirmOpen] = useState(false);
  const [reason, setReason] = useState("");

  const isPending = request.status === "pending";
  const videoBlobUrl = useAuthedMediaUrl(request.video_url);
  const audioBlobUrl = useAuthedMediaUrl(request.audio_url);

  async function handleApprove() {
    try {
      await approve.mutateAsync(request.id);
      toast.success("Voice clone approved — it's now usable on agents");
      setApproveConfirmOpen(false);
    } catch (err) {
      toast.error(platformApiErrorMessage(err, "Couldn't approve request"));
    }
  }

  async function handleReject() {
    try {
      await reject.mutateAsync({ id: request.id, reason: reason.trim() });
      toast.success("Request rejected");
      setRejectConfirmOpen(false);
      setReason("");
    } catch (err) {
      toast.error(platformApiErrorMessage(err, "Couldn't reject request"));
    }
  }

  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-heading text-lg font-semibold">{request.name}</p>
            <p className="text-sm text-muted-foreground">
              {request.org_name} &middot; {request.user_name ?? "Unknown user"}
              {request.user_email ? ` (${request.user_email})` : ""}
            </p>
            <p className="text-xs text-muted-foreground">Submitted {formatDate(request.created_at)}</p>
          </div>
          <Badge variant={STATUS_VARIANT[request.status] ?? "warning"} className="capitalize">
            {request.status}
          </Badge>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Consent video</p>
            <video src={videoBlobUrl} controls className="w-full rounded-lg border border-border" />
            <p className="text-xs italic text-muted-foreground">
              Script: &ldquo;{VOICE_CLONING_CONSENT_SCRIPT}&rdquo;
            </p>
          </div>
          <div className="space-y-1.5">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Voice sample</p>
            <audio src={audioBlobUrl} controls className="w-full" />
          </div>
        </div>

        {request.status === "rejected" && request.rejection_reason && (
          <p className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            Rejection reason: {request.rejection_reason}
          </p>
        )}

        {isPending && (
          <div className="space-y-3 border-t border-border pt-4">
            <div className="space-y-1.5">
              <Textarea
                placeholder="Reason for rejection (required to reject)"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </div>
            <div className="flex gap-2">
              <Button variant="gradient" onClick={() => setApproveConfirmOpen(true)}>
                <Check className="h-3.5 w-3.5" /> Approve
              </Button>
              <Button variant="destructive" onClick={() => setRejectConfirmOpen(true)} disabled={!reason.trim()}>
                <X className="h-3.5 w-3.5" /> Reject
              </Button>
            </div>
          </div>
        )}
      </CardContent>

      <ConfirmDialog
        open={approveConfirmOpen}
        onOpenChange={setApproveConfirmOpen}
        title="Approve this voice clone?"
        description={`This calls ElevenLabs to create the real voice for ${request.org_name} right now, and it becomes selectable on their agents immediately.`}
        confirmLabel="Approve"
        loading={approve.isPending}
        onConfirm={handleApprove}
      />

      <ConfirmDialog
        open={rejectConfirmOpen}
        onOpenChange={setRejectConfirmOpen}
        title="Reject this request?"
        description={reason.trim() ? `${request.org_name} will see: "${reason.trim()}"` : "Enter a reason first."}
        confirmLabel="Reject"
        variant="destructive"
        loading={reject.isPending}
        onConfirm={handleReject}
      />
    </Card>
  );
}
