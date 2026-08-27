import { Mail, MapPin, Phone } from "lucide-react";

// Real contact channels only -- no contact form here on purpose, since there's
// nowhere on this static marketing site for a submission to go without a
// backend endpoint. Direct email/phone/address instead, same info as
// PrivacyPolicy.tsx's Section 13 (Contact Us / Grievance Officer) for the
// address, kept consistent across both pages.
const channels = [
  {
    icon: Mail,
    label: "Email",
    value: "support@quickhowl.com",
    href: "mailto:support@quickhowl.com",
  },
  {
    icon: Phone,
    label: "Phone",
    value: "+91 83086 55418",
    href: "tel:+918308655418",
  },
  {
    icon: MapPin,
    label: "Address",
    value: "Wagholi, Pune, Maharashtra, India",
    href: undefined,
  },
];

export function Contact() {
  return (
    <section id="contact" className="section-pad border-t border-border/60 bg-card/30">
      <div className="reveal-on-scroll mx-auto max-w-4xl px-4 text-center sm:px-6 lg:px-8">
        <p className="eyebrow text-primary">Contact</p>
        <h2 className="mt-3 font-heading text-3xl font-semibold sm:text-4xl">Talk to us</h2>
        <p className="mt-4 text-muted-foreground">
          Questions about the platform, a plan, or anything else — reach out directly and a real person will get
          back to you.
        </p>

        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          {channels.map((c) => {
            const content = (
              <>
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 text-primary">
                  <c.icon className="h-5 w-5" />
                </span>
                <span className="mt-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {c.label}
                </span>
                <span className="mt-1 text-sm font-medium text-foreground">{c.value}</span>
              </>
            );
            const className =
              "hover-lift flex flex-col items-center rounded-2xl border border-border bg-card p-6 shadow-[var(--shadow-card)]";
            return c.href ? (
              <a key={c.label} href={c.href} className={className}>
                {content}
              </a>
            ) : (
              <div key={c.label} className={className}>
                {content}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
