import { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { Logo } from "@/components/shared/Logo";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const links = [
  { to: "/#features", label: "Features" },
  { to: "/#how-it-works", label: "How it works" },
  { to: "/#pricing", label: "Pricing" },
];

export function PublicNav() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur-lg">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link to="/">
          <Logo />
        </Link>

        <nav className="hidden items-center gap-8 md:flex">
          {links.map((l) => (
            <a key={l.to} href={l.to} className="text-sm text-muted-foreground transition-colors hover:text-foreground">
              {l.label}
            </a>
          ))}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <ThemeToggle />
          <div className="h-6 w-px bg-border" />
          <Button variant="ghost" asChild>
            <NavLink to="/login">Log in</NavLink>
          </Button>
          <Button variant="gradient" asChild>
            <NavLink to="/signup">Get started</NavLink>
          </Button>
        </div>

        <button className="md:hidden" onClick={() => setOpen((v) => !v)} aria-label="Toggle menu">
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      <div className={cn("overflow-hidden border-t border-border/60 md:hidden", open ? "max-h-80" : "max-h-0")}>
        <div className="flex flex-col gap-1 px-4 py-3">
          {links.map((l) => (
            <a key={l.to} href={l.to} className="rounded-md px-2 py-2 text-sm text-muted-foreground hover:bg-accent">
              {l.label}
            </a>
          ))}
          <div className="mt-2 flex items-center justify-between gap-2 px-2">
            <span className="text-sm text-muted-foreground">Theme</span>
            <ThemeToggle />
          </div>
          <div className="mt-2 flex gap-2">
            <Button variant="outline" className="flex-1" asChild>
              <NavLink to="/login">Log in</NavLink>
            </Button>
            <Button variant="gradient" className="flex-1" asChild>
              <NavLink to="/signup">Get started</NavLink>
            </Button>
          </div>
        </div>
      </div>
    </header>
  );
}
