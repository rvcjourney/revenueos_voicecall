import { Check, PhoneForwarded, ShieldCheck, Users2 } from "lucide-react";

// Wireframe's "Enterprise-grade" 3-card checklist + badge row, populated with
// the 3 remaining existing features not covered by PlatformPillars.tsx
// (compliance, role-based access, bring-your-own-number). Each checklist
// item is a clause already present in that feature's original description
// in Landing.tsx, split into list form — not new information.
const cards = [
  {
    icon: ShieldCheck,
    title: "Compliance you can trust",
    description: "Compliance without the busywork — built in, not bolted on.",
    items: ["Org-level Do Not Call lists", "Automatic enforcement against India's TRAI NCPR registry"],
  },
  {
    icon: Users2,
    title: "Role-based team access",
    description: "Admins manage everything; reps get exactly the access they need.",
    items: ["Admins manage the full org", "Reps request access per agent", "Per-agent edit permissions"],
  },
  {
    icon: PhoneForwarded,
    title: "Bring your own number",
    description: "Connect your existing SIP trunk with a guided verify-and-test flow.",
    items: ["Works with any SIP trunk", "Guided verify-and-test flow", "No engineering ticket needed"],
  },
];

const badges = ["TRAI NCPR compliance", "Org-level DNC lists", "Role-based access"];

export function EnterpriseGrade() {
  return (
    <section className="section-pad border-t border-border/60">
      <div className="reveal-on-scroll mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow">Enterprise-grade</p>
          <h2 className="mt-3 font-heading text-3xl font-semibold sm:text-4xl">Compliance, control, and confidence</h2>
        </div>
        <div className="mt-12 grid gap-6 lg:grid-cols-3">
          {cards.map((c) => (
            <div key={c.title} className="rounded-2xl border border-border bg-card p-7 shadow-[var(--shadow-card)]">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 text-primary">
                <c.icon className="h-5 w-5" />
              </span>
              <h4 className="mt-4 text-lg font-semibold">{c.title}</h4>
              <p className="mt-2 text-sm text-muted-foreground">{c.description}</p>
              <ul className="mt-5 space-y-2.5">
                {c.items.map((item) => (
                  <li key={item} className="flex items-start gap-2.5 text-sm text-muted-foreground">
                    <span className="mt-0.5 flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-full bg-success/15">
                      <Check className="h-3 w-3 text-success" strokeWidth={3} />
                    </span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-10 flex flex-wrap justify-center gap-2">
          {badges.map((b) => (
            <span
              key={b}
              className="rounded-full border border-border bg-card px-4 py-2 text-xs font-semibold text-muted-foreground"
            >
              {b}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
