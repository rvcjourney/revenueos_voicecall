import { Check, X } from "lucide-react";

// Head-to-head comparison of a traditional dialer team vs. QuickHowl AI voice
// agents. Each pairing is the same dimension (volume, ramp, cost, ...) framed
// both ways, so the two columns read row-for-row even though they're rendered
// as two separate cards for a clean mobile stack.
const comparison = [
  {
    dimension: "Call volume",
    traditional: "~70 dials per rep per day — and it drops as fatigue sets in",
    quickhowl: "Hundreds of calls running concurrently, with no drop-off",
  },
  {
    dimension: "Time to ramp",
    traditional: "Weeks of hiring, onboarding, and script training per rep",
    quickhowl: "Configure an agent and go live in under 10 minutes",
  },
  {
    dimension: "Cost to scale",
    traditional: "Linear — every extra 100 calls a day means another hire",
    quickhowl: "Flat — one platform absorbs the extra volume",
  },
  {
    dimension: "Consistency",
    traditional: "Pitch, tone, and energy vary by rep, mood, and time of day",
    quickhowl: "The same qualified pitch and tone on every single call",
  },
  {
    dimension: "Compliance",
    traditional: "Manual DNC checks that are easy to skip under pressure",
    quickhowl: "Automatic TRAI NCPR + Do-Not-Call screening before every dial",
  },
  {
    dimension: "Reporting",
    traditional: "Hand-typed call logs, patchy notes, and guesswork",
    quickhowl: "Live analytics, full transcripts, and AI summaries on every call",
  },
  {
    dimension: "Language",
    traditional: "Hindi or English depends on who's on shift",
    quickhowl: "Natural Hindi and English on every call, all day",
  },
];

export function WhyVoiceAgents() {
  return (
    <section className="section-pad border-t border-border/60 bg-card/30">
      <div className="reveal-on-scroll mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow">Why AI voice agents</p>
          <h2 className="mt-3 font-heading text-3xl font-semibold sm:text-4xl">
            The math stops working with a room full of dialers
          </h2>
          <p className="mt-3 text-muted-foreground">
            Traditional outbound scales by adding people. AI voice agents scale by adding volume — with the same
            pitch, the same compliance, on every call.
          </p>
        </div>

        <div className="mt-12 grid gap-6 lg:grid-cols-2">
          <div className="rounded-2xl border border-border bg-card p-7 shadow-[var(--shadow-card)]">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Traditional calling</p>
            <ul className="mt-5 space-y-4">
              {comparison.map((c) => (
                <li key={c.dimension} className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-destructive/15">
                    <X className="h-3 w-3 text-destructive" strokeWidth={3} />
                  </span>
                  <span className="text-sm text-muted-foreground">
                    <span className="font-medium text-foreground/80">{c.dimension}:</span> {c.traditional}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-2xl border border-primary/60 bg-card p-7 shadow-[var(--shadow-glow)]">
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">QuickHowl AI voice agents</p>
            <ul className="mt-5 space-y-4">
              {comparison.map((c) => (
                <li key={c.dimension} className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-success/15">
                    <Check className="h-3 w-3 text-success" strokeWidth={3} />
                  </span>
                  <span className="text-sm text-foreground/90">
                    <span className="font-medium">{c.dimension}:</span> {c.quickhowl}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
