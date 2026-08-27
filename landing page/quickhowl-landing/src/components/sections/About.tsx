import { Globe2, ShieldCheck, Sparkles } from "lucide-react";

// Distinct from Hero.tsx's product pitch ("what QuickHowl does") -- this is
// "who QuickHowl is for and why it exists," specifically the India-first
// positioning that generic global voice-AI platforms don't compete on.
const pillars = [
  {
    icon: Sparkles,
    title: "Built for how India actually talks",
    description:
      "Hinglish isn't a translation layer bolted onto an English model — it's the default. Your agent code-switches the way a real salesperson on a call would.",
  },
  {
    icon: ShieldCheck,
    title: "Compliance-first, not compliance-later",
    description:
      "TRAI NCPR checks and Do-Not-Call enforcement run on every single call automatically, not as an afterthought you have to configure or a feature buried in an enterprise tier.",
  },
  {
    icon: Globe2,
    title: "For Indian sales teams, not just Indian users",
    description:
      "Most voice-AI platforms are built globally-first and treat Indian calling norms — language, timing, regulation — as a localization checkbox. We built it the other way round.",
  },
];

export function About() {
  return (
    <section id="about" className="section-pad border-t border-border/60">
      <div className="reveal-on-scroll mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow text-primary">About QuickHowl</p>
          <h2 className="mt-3 font-heading text-3xl font-semibold sm:text-4xl">
            An AI calling platform built for the Indian market, not adapted for it
          </h2>
          <p className="mt-4 text-muted-foreground">
            QuickHowl exists because most outbound sales calling still means a room full of people dialing numbers
            one at a time, and most "AI voice agent" platforms are built for a US-first market and retrofitted with
            an Indian language pack. We started from the opposite end: Hinglish conversations, India's calling
            regulations, and Indian sales workflows as the default, not an add-on.
          </p>
        </div>

        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {pillars.map((p) => (
            <div key={p.title} className="rounded-2xl border border-border bg-card p-7 shadow-[var(--shadow-card)]">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 text-primary">
                <p.icon className="h-5 w-5" />
              </span>
              <h4 className="mt-4 text-lg font-semibold">{p.title}</h4>
              <p className="mt-2 text-sm text-muted-foreground">{p.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
