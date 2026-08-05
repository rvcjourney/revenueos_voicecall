import { Link } from "react-router-dom";
import { Logo } from "@/components/shared/Logo";

const columns = [
  {
    title: "Product",
    links: [
      { label: "Features", href: "/#features" },
      { label: "How it works", href: "/#how-it-works" },
      { label: "Pricing", href: "/#pricing" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "About", href: "/#" },
      { label: "Contact", href: "/#faq" },
    ],
  },
  {
    title: "Legal",
    links: [
      { label: "Privacy Policy", href: "/#" },
      { label: "Terms of Service", href: "/#" },
      { label: "TRAI / DNC Compliance", href: "/#" },
    ],
  },
];

export function PublicFooter() {
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
          <Link to="/login" className="hover:text-foreground">
            Log in
          </Link>
        </p>
      </div>
    </footer>
  );
}
