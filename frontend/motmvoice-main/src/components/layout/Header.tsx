import { Link, useRouterState } from "@tanstack/react-router";
import { Bell, Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";

export function Header() {
  const path     = useRouterState({ select: (s) => s.location.pathname });
  const segments = path.split("/").filter(Boolean);

  return (
    <header className="sticky top-0 z-40 h-16 bg-background/80 backdrop-blur border-b border-border flex items-center px-6 gap-4">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm text-muted-foreground">
        {segments.map((s, i) => (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && <span className="opacity-40">/</span>}
            <span className={`capitalize ${i === segments.length - 1 ? "text-foreground font-medium" : ""}`}>
              {s.replace(/-/g, " ")}
            </span>
          </span>
        ))}
      </nav>

      {/* Search */}
      <div className="flex-1 max-w-sm mx-auto relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
        <input
          placeholder="Search…"
          className="w-full pl-9 pr-4 h-9 rounded-lg bg-surface-2 border border-border text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 transition-colors"
        />
      </div>

      {/* Right actions */}
      <div className="flex items-center gap-2 ml-auto">
        {/* Notification bell */}
        <button className="relative h-9 w-9 grid place-items-center rounded-lg hover:bg-surface-2 text-muted-foreground hover:text-foreground transition-colors">
          <Bell className="h-4 w-4" />
          <span className="absolute top-2 right-2 h-1.5 w-1.5 rounded-full bg-destructive ring-2 ring-background" />
        </button>

        {/* New Campaign */}
        <Link to="/campaigns/new">
          <Button size="sm" className="bg-gradient-primary text-white shadow-glow hover:opacity-90 gap-1.5">
            <Plus className="h-3.5 w-3.5" />
            New Campaign
          </Button>
        </Link>
      </div>
    </header>
  );
}
