export type CampaignStatus =
  | "running" | "active" | "paused" | "completed"
  | "draft"   | "scheduled" | "failed";

export type CallOutcome =
  | "interested" | "completed" | "not_interested"
  | "no_answer"  | "failed"    | "in_progress" | "pending";

// ── Badge tokens ─────────────────────────────────────────────────────────────
// Each status gets: bg, text, border, glowColor, and optional dotColor
type BadgeToken = {
  bg:     string;   // semi-transparent background
  text:   string;   // text colour
  border: string;   // border colour
  glow?:  string;   // box-shadow glow (optional)
  dot?:   string;   // indicator dot colour (optional)
  pulse?: boolean;  // animate the dot?
};

const outcomeTokens: Record<string, BadgeToken> = {
  interested: {
    bg:     "oklch(0.70 0.16 160 / 0.12)",
    text:   "oklch(0.75 0.14 160)",
    border: "oklch(0.70 0.16 160 / 0.30)",
    glow:   "0 0 10px oklch(0.70 0.16 160 / 0.20)",
    dot:    "oklch(0.70 0.16 160)",
  },
  completed: {
    bg:     "oklch(0.565 0.240 284 / 0.12)",
    text:   "oklch(0.75 0.14 284)",
    border: "oklch(0.565 0.240 284 / 0.30)",
    glow:   "0 0 10px oklch(0.565 0.240 284 / 0.18)",
  },
  not_interested: {
    bg:     "oklch(0.145 0.015 270 / 0.80)",
    text:   "oklch(0.55 0.010 270)",
    border: "oklch(0.22 0.012 270 / 0.60)",
  },
  no_answer: {
    bg:     "oklch(0.62 0.20 18 / 0.12)",
    text:   "oklch(0.76 0.14 16)",
    border: "oklch(0.62 0.20 18 / 0.30)",
    glow:   "0 0 8px oklch(0.62 0.20 18 / 0.15)",
  },
  failed: {
    bg:     "oklch(0.62 0.23 25 / 0.12)",
    text:   "oklch(0.72 0.18 25)",
    border: "oklch(0.62 0.23 25 / 0.30)",
    glow:   "0 0 8px oklch(0.62 0.23 25 / 0.18)",
  },
  in_progress: {
    bg:     "oklch(0.78 0.16 75 / 0.12)",
    text:   "oklch(0.82 0.13 75)",
    border: "oklch(0.78 0.16 75 / 0.30)",
    dot:    "oklch(0.78 0.16 75)",
    pulse:  true,
  },
  pending: {
    bg:     "oklch(0.130 0.013 270 / 0.80)",
    text:   "oklch(0.50 0.010 270)",
    border: "oklch(0.20 0.012 270 / 0.50)",
  },
  callback_requested: {
    bg:     "oklch(0.72 0.18 55 / 0.12)",
    text:   "oklch(0.80 0.15 55)",
    border: "oklch(0.72 0.18 55 / 0.30)",
    glow:   "0 0 8px oklch(0.72 0.18 55 / 0.18)",
    dot:    "oklch(0.80 0.15 55)",
  },
  do_not_call: {
    bg:     "oklch(0.62 0.23 25 / 0.10)",
    text:   "oklch(0.65 0.18 25)",
    border: "oklch(0.62 0.23 25 / 0.25)",
  },
  wrong_number: {
    bg:     "oklch(0.130 0.013 270 / 0.80)",
    text:   "oklch(0.50 0.010 270)",
    border: "oklch(0.20 0.012 270 / 0.50)",
  },
  voicemail: {
    bg:     "oklch(0.545 0.220 252 / 0.10)",
    text:   "oklch(0.65 0.14 252)",
    border: "oklch(0.545 0.220 252 / 0.25)",
  },
};

const outcomeLabel: Record<string, string> = {
  interested:          "Interested",
  completed:           "Completed",
  not_interested:      "Not Interested",
  no_answer:           "No Answer",
  failed:              "Failed",
  in_progress:         "In Progress",
  pending:             "Pending",
  callback_requested:  "Callback",
  do_not_call:         "Do Not Call",
  wrong_number:        "Wrong Number",
  voicemail:           "Voicemail",
};

// ── Outcome Badge ─────────────────────────────────────────────────────────────
export function OutcomeBadge({ outcome }: { outcome: string }) {
  const t     = outcomeTokens[outcome] ?? outcomeTokens.pending;
  const label = outcomeLabel[outcome] ?? outcome;

  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold transition-all duration-150"
      style={{
        background:  t.bg,
        color:       t.text,
        border:      `1px solid ${t.border}`,
        boxShadow:   t.glow,
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
      }}
    >
      {t.dot && (
        <span
          className={`h-1.5 w-1.5 rounded-full shrink-0 ${t.pulse ? "badge-shimmer" : ""}`}
          style={{ background: t.dot, boxShadow: `0 0 4px ${t.dot}` }}
        />
      )}
      {label}
    </span>
  );
}

// ── Campaign badge tokens ─────────────────────────────────────────────────────
const campTokens: Record<string, BadgeToken> = {
  running: {
    bg:     "oklch(0.70 0.16 160 / 0.12)",
    text:   "oklch(0.75 0.14 160)",
    border: "oklch(0.70 0.16 160 / 0.28)",
    glow:   "0 0 12px oklch(0.70 0.16 160 / 0.22)",
    dot:    "oklch(0.70 0.16 160)",
    pulse:  true,
  },
  active: {
    bg:     "oklch(0.70 0.16 160 / 0.12)",
    text:   "oklch(0.75 0.14 160)",
    border: "oklch(0.70 0.16 160 / 0.28)",
    glow:   "0 0 12px oklch(0.70 0.16 160 / 0.22)",
    dot:    "oklch(0.70 0.16 160)",
    pulse:  true,
  },
  paused: {
    bg:     "oklch(0.78 0.16 75 / 0.12)",
    text:   "oklch(0.82 0.13 75)",
    border: "oklch(0.78 0.16 75 / 0.28)",
    dot:    "oklch(0.78 0.16 75)",
    pulse:  false,
  },
  completed: {
    bg:     "oklch(0.565 0.240 284 / 0.12)",
    text:   "oklch(0.75 0.14 284)",
    border: "oklch(0.565 0.240 284 / 0.28)",
    glow:   "0 0 8px oklch(0.565 0.240 284 / 0.15)",
  },
  draft: {
    bg:     "oklch(0.130 0.013 270 / 0.80)",
    text:   "oklch(0.50 0.010 270)",
    border: "oklch(0.20 0.012 270 / 0.50)",
  },
  scheduled: {
    bg:     "oklch(0.545 0.220 252 / 0.12)",
    text:   "oklch(0.72 0.14 252)",
    border: "oklch(0.545 0.220 252 / 0.28)",
    glow:   "0 0 8px oklch(0.545 0.220 252 / 0.15)",
    dot:    "oklch(0.72 0.14 252)",
  },
  failed: {
    bg:     "oklch(0.62 0.23 25 / 0.12)",
    text:   "oklch(0.72 0.18 25)",
    border: "oklch(0.62 0.23 25 / 0.28)",
    glow:   "0 0 8px oklch(0.62 0.23 25 / 0.18)",
  },
};

// ── Campaign Badge ────────────────────────────────────────────────────────────
export function CampaignBadge({ status }: { status: string }) {
  const t = campTokens[status] ?? campTokens.draft;

  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold capitalize transition-all duration-150"
      style={{
        background:  t.bg,
        color:       t.text,
        border:      `1px solid ${t.border}`,
        boxShadow:   t.glow,
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
      }}
    >
      {t.dot && (
        <span
          className={`h-1.5 w-1.5 rounded-full shrink-0 ${t.pulse ? "pulse-dot" : ""}`}
          style={{ background: t.dot, boxShadow: `0 0 5px ${t.dot}` }}
        />
      )}
      {status}
    </span>
  );
}
