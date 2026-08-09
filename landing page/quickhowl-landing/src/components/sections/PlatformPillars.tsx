import { FileText, LineChart, Mic } from "lucide-react";

// Wireframe's "Full-stack platform" 3-card + link-row section, populated with
// the same 10 feature entries from the original Landing.tsx `features` array
// (grouped into 3 pillars, condensed to short link labels) — no new claims,
// just a different presentation of existing copy. Grouping:
//   Voices:    voice cloning, multilingual voice
//   Campaigns: bulk import, concurrent calling, live dashboard
//   Insights:  transcripts & AI summaries, segmented exports
// (Role-based access, built-in compliance, and bring-your-own-number are
// covered in the Enterprise-grade section below instead.)
const pillars = [
  {
    icon: Mic,
    title: "Voices",
    description: "Human-like, multilingual voice cloning for every AI agent you run.",
    links: [
      { label: "Voice cloning", meta: "60s sample" },
      { label: "Multilingual voice", meta: "20+ languages" },
    ],
  },
  {
    icon: LineChart,
    title: "Campaigns",
    description: "Bulk contact import, concurrent batch calling, and a live campaign dashboard.",
    links: [
      { label: "Bulk contact import", meta: "CSV / Excel" },
      { label: "Concurrent batch calling", meta: "hundreds at once" },
      { label: "Live campaign dashboard", meta: "real-time" },
    ],
  },
  {
    icon: FileText,
    title: "Insights",
    description: "Transcripts, AI summaries, sentiment tags, and segmented exports.",
    links: [
      { label: "Transcripts & AI summaries", meta: "every call" },
      { label: "Segmented exports", meta: "one click" },
    ],
  },
];

export function PlatformPillars() {
  return (
    <section id="features" className="section-pad border-t border-border/60 bg-card/30">
      <div className="reveal-on-scroll mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow">Full-stack platform</p>
          <h2 className="mt-3 font-heading text-3xl font-semibold sm:text-4xl">Everything your outbound team needs to scale</h2>
          <p className="mt-3 text-muted-foreground">From first dial to closed deal, in one platform built for high-volume B2B sales teams.</p>
        </div>
        <div className="mt-12 grid gap-6 lg:grid-cols-3">
          {pillars.map((p) => (
            <div key={p.title} className="rounded-2xl border border-border bg-card p-7 shadow-[var(--shadow-card)]">
              <div className="mb-5 flex h-24 items-center justify-center rounded-xl bg-accent">
                <p.icon className="h-9 w-9 text-primary" />
              </div>
              <h4 className="text-lg font-semibold">{p.title}</h4>
              <p className="mt-2 text-sm text-muted-foreground">{p.description}</p>
              <div className="mt-5 flex flex-col gap-2">
                {p.links.map((l) => (
                  <div
                    key={l.label}
                    className="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2.5 text-sm font-medium"
                  >
                    <span>{l.label}</span>
                    <span className="text-xs font-normal text-muted-foreground">{l.meta}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
