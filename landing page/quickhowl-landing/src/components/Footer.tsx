import { Logo } from "@/components/shared/Logo";
import { LOGIN_URL } from "@/lib/env";

const columns = [
  {
    title: "Product",
    links: [
      { label: "Features", href: "#features" },
      { label: "How it works", href: "#how-it-works" },
      { label: "Pricing", href: "#pricing" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "About", href: "#about" },
      { label: "Contact", href: "#contact" },
    ],
  },
  {
    title: "Legal",
    links: [
      { label: "Privacy Policy", href: "/privacy-policy" },
      { label: "Terms of Service", href: "/terms-of-service" },
      { label: "TRAI / DNC Compliance", href: "/terms-of-service#trai-dnc-compliance" },
    ],
  },
];

export function Footer() {
  return (
    <footer className="border-t border-border/60 bg-card/40">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr_1fr] lg:px-8">
        <div className="space-y-3">
          <Logo />
          <p className="max-w-xs text-sm text-muted-foreground">
            AI voice agents that make real outbound sales calls, in Hinglish and 20+ languages, at scale.
          </p>
        </div>
        {columns.map((col) => (
          <div key={col.title} className="space-y-3">
            <p className="text-sm font-semibold text-foreground">{col.title}</p>
            <ul className="space-y-2">
              {col.links.map((l) => (
                <li key={l.label}>
                  <a href={l.href} className="text-sm text-muted-foreground hover:text-foreground">
                    {l.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-border/60 py-6 text-center text-xs text-muted-foreground">
        <p>
          © {new Date().getFullYear()} QuickHowl. All rights reserved. ·{" "}
          <a href={LOGIN_URL} className="hover:text-foreground">
            Log in
          </a>
        </p>
      </div>
    </footer>
  );
}
