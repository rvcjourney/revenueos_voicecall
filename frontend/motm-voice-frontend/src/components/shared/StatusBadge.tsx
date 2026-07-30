import { cn, titleCase } from "@/lib/utils";
import type { BadgeProps } from "@/components/ui/badge";

type Tone = "success" | "warning" | "destructive" | "info" | "muted" | "secondary" | "default";

const toneClasses: Record<Tone, string> = {
  success: "border-transparent bg-success/15 text-success",
  warning: "border-transparent bg-warning/15 text-warning",
  destructive: "border-transparent bg-destructive/15 text-destructive",
  info: "border-transparent bg-info/15 text-info",
  muted: "border-transparent bg-muted text-muted-foreground",
  secondary: "border-transparent bg-secondary text-secondary-foreground",
  default: "border-transparent bg-primary/15 text-primary",
};

const pulseTones: Tone[] = ["success"];

const campaignToneMap: Record<string, Tone> = {
  draft: "muted",
  scheduled: "info",
  running: "success",
  paused: "warning",
  completed: "success",
  failed: "destructive",
};

const callOutcomeToneMap: Record<string, Tone> = {
  interested: "success",
  not_interested: "muted",
  no_answer: "muted",
  callback_requested: "secondary",
  voicemail: "info",
  wrong_number: "warning",
  do_not_call: "muted",
  pending: "warning",
};

const callStatusToneMap: Record<string, Tone> = {
  initiated: "info",
  ringing: "info",
  connected: "success",
  completed: "secondary",
  no_answer: "muted",
  busy: "warning",
  failed: "destructive",
  cancelled: "muted",
};

const contactStatusToneMap: Record<string, Tone> = {
  pending: "muted",
  dialing: "info",
  completed: "success",
  no_answer: "muted",
  failed: "destructive",
  do_not_call: "muted",
  queue_timeout: "warning",
};

const agentAccessToneMap: Record<string, Tone> = {
  approved: "success",
  pending: "warning",
  locked: "muted",
};

const sentimentToneMap: Record<string, Tone> = {
  positive: "success",
  neutral: "muted",
  negative: "destructive",
};

function Pill({ label, tone, className, ...props }: { label: string; tone: Tone } & Omit<BadgeProps, "variant">) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        toneClasses[tone],
        className
      )}
      {...props}
    >
      {pulseTones.includes(tone) && <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse-glow" />}
      {label}
    </span>
  );
}

export function CampaignStatusBadge({ status, className }: { status: string; className?: string }) {
  return <Pill label={titleCase(status)} tone={campaignToneMap[status] ?? "muted"} className={className} />;
}

export function CallOutcomeBadge({ outcome, className }: { outcome: string; className?: string }) {
  return <Pill label={titleCase(outcome)} tone={callOutcomeToneMap[outcome] ?? "muted"} className={className} />;
}

export function CallStatusBadge({ status, className }: { status: string; className?: string }) {
  return <Pill label={titleCase(status)} tone={callStatusToneMap[status] ?? "muted"} className={className} />;
}

export function ContactStatusBadge({ status, className }: { status: string; className?: string }) {
  return <Pill label={titleCase(status)} tone={contactStatusToneMap[status] ?? "muted"} className={className} />;
}

export function AgentAccessBadge({ status, className }: { status: string; className?: string }) {
  return <Pill label={titleCase(status)} tone={agentAccessToneMap[status] ?? "muted"} className={className} />;
}

export function RoleBadge({ role, className }: { role: string; className?: string }) {
  return <Pill label={titleCase(role)} tone={role === "admin" ? "default" : "muted"} className={className} />;
}

export function SentimentBadge({ sentiment, className }: { sentiment: string; className?: string }) {
  return <Pill label={titleCase(sentiment)} tone={sentimentToneMap[sentiment] ?? "muted"} className={className} />;
}
