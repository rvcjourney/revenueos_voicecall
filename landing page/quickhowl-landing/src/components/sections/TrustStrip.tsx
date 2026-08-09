const industries = [
  "B2B SaaS",
  "Real Estate",
  "Fintech",
  "Healthcare",
  "EdTech",
  "D2C & Retail",
  "Insurance",
  "Financial Services",
];

export function TrustStrip() {
  return (
    <section className="border-t border-border/60 py-10">
      <div className="reveal-on-scroll">
        <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          Built for outbound teams across industries
        </p>
        <div className="marquee-mask mt-6">
          <div className="marquee-track">
            {[...industries, ...industries].map((name, i) => (
              <span key={`${name}-${i}`} className="font-heading text-base font-bold text-muted-foreground/70">
                {name}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
