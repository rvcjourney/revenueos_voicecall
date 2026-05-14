import { Link, useRouterState } from "@tanstack/react-router";
import { Bell, Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";

export function Header() {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const segments = path.split("/").filter(Boolean);
  return (
    <header className="sticky top-0 z-40 h-16 bg-background/80 backdrop-blur border-b border-border flex items-center px-6 gap-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        {segments.map((s, i) => (
          <span key={i} className="flex items-center gap-2">
            {i > 0 && <span>/</span>}
            <span className={i === segments.length - 1 ? "text-foreground capitalize" : "capitalize"}>{s.replace(/-/g, " ")}</span>
          </span>
        ))}
      </div>
      <div className="flex-1 max-w-md mx-auto relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <input
          placeholder="Search calls, contacts, campaigns…"
          className="w-full pl-9 pr-16 h-9 rounded-md bg-surface-2 border border-border text-sm placeholder:text-muted-foreground focus:outline-none focus:border-primary/50"
        />
        <kbd className="absolute right-3 top-1/2 -translate-y-1/2 hidden sm:inline-block text-[10px] font-mono px-1.5 py-0.5 rounded border border-border bg-surface-3 text-muted-foreground">⌘K</kbd>
      </div>
      <button className="relative h-9 w-9 grid place-items-center rounded-md hover:bg-surface-2 text-muted-foreground hover:text-foreground">
        <Bell className="h-4 w-4" />
        <span className="absolute top-2 right-2 h-2 w-2 rounded-full bg-destructive" />
      </button>
      <Link to="/campaigns/new">
        <Button size="sm" className="bg-gradient-primary text-white shadow-glow hover:opacity-90">
          <Plus className="h-4 w-4" /> New Campaign
        </Button>
      </Link>
    </header>
  );
}
