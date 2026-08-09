const featured = {
  quote: "We 4x'd our outbound reach without hiring a single extra SDR — and the Hinglish agent genuinely sounds like a person.",
  name: "VP of Sales",
  org: "B2B SaaS company",
};

const supporting = [
  {
    quote: "Setup took an afternoon. Within a week we had a full pipeline of interested leads flowing straight into our CRM.",
    name: "RevOps Manager",
    org: "Manufacturing distributor",
  },
  {
    quote: "Built-in DNC and TRAI compliance gave our legal team the confidence to greenlight this immediately — no back-and-forth.",
    name: "Head of Growth",
    org: "Fintech startup",
  },
];

export function Testimonials() {
  return (
    <section className="section-pad border-t border-border/60">
      <div className="reveal-on-scroll mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="font-heading text-3xl font-semibold sm:text-4xl">Loved by sales teams scaling outbound, everywhere</h2>
        </div>

        <div className="mt-12 grid gap-6 rounded-2xl border border-border bg-card p-10 shadow-[var(--shadow-card)] lg:grid-cols-[1fr_auto] lg:items-center">
          <div>
            <p className="font-heading text-xl font-semibold leading-snug sm:text-2xl">"{featured.quote}"</p>
            <div className="mt-6 flex items-center gap-3">
              <span className="h-10 w-10 rounded-full bg-[image:var(--gradient-primary)]" />
              <div>
                <p className="text-sm font-semibold">{featured.name}</p>
                <p className="text-xs text-muted-foreground">{featured.org}</p>
              </div>
            </div>
          </div>
          <div className="text-center lg:w-44 lg:border-l lg:border-border lg:pl-8">
            <p className="stat-figure text-4xl font-extrabold text-primary">1,200+</p>
            <p className="mt-1 text-sm text-muted-foreground">AI sales calls running now</p>
          </div>
        </div>

        <div className="mt-6 grid gap-6 md:grid-cols-2">
          {supporting.map((t) => (
            <div key={t.name} className="rounded-2xl border border-border bg-card p-6 shadow-[var(--shadow-card)]">
              <p className="text-sm leading-relaxed text-foreground/90">"{t.quote}"</p>
              <div className="mt-4">
                <p className="text-sm font-medium">{t.name}</p>
                <p className="text-xs text-muted-foreground">{t.org}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
