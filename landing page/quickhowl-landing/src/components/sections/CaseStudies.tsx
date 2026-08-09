// Wireframe's "Case studies" 3-card grid, populated with the same 3
// testimonials used in Testimonials.tsx (the wireframe itself reuses its one
// testimonial in both its case-grid and its big-testimonial section, so
// reusing all 3 here too is consistent with the source design). Each card's
// "stat" is extracted from language already present in that exact quote —
// not a new number invented for this layout.
const cases = [
  {
    org: "B2B SaaS company",
    stat: "4x",
    statLabel: "outbound reach, no new hires",
    quote: "We 4x'd our outbound reach without hiring a single extra SDR — and the Hinglish agent genuinely sounds like a person.",
  },
  {
    org: "Manufacturing distributor",
    stat: "1 week",
    statLabel: "to a full pipeline",
    quote: "Setup took an afternoon. Within a week we had a full pipeline of interested leads flowing straight into our CRM.",
  },
  {
    org: "Fintech startup",
    stat: "0",
    statLabel: "back-and-forth with legal",
    quote: "Built-in DNC and TRAI compliance gave our legal team the confidence to greenlight this immediately — no back-and-forth.",
  },
];

export function CaseStudies() {
  return (
    <section className="section-pad border-t border-border/60">
      <div className="reveal-on-scroll mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow">Case studies</p>
          <h2 className="mt-3 font-heading text-3xl font-semibold sm:text-4xl">Trusted by outbound teams scaling fast</h2>
        </div>
        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {cases.map((c) => (
            <div key={c.org} className="rounded-2xl border border-border bg-card p-7 shadow-[var(--shadow-card)]">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{c.org}</p>
              <p className="stat-figure mt-4 text-3xl font-extrabold text-primary">{c.stat}</p>
              <p className="mt-1 text-sm text-muted-foreground">{c.statLabel}</p>
              <p className="mt-5 text-sm leading-relaxed text-foreground/90">"{c.quote}"</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
