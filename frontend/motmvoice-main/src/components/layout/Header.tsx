import { Link, useRouterState } from "@tanstack/react-router";
import { Bell, Plus, Search, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

// Map route keys → human labels for breadcrumb
const LABELS: Record<string, string> = {
  dashboard:  "Dashboard",
  campaigns:  "Campaigns",
  calls:      "Call History",
  agents:     "AI Agents",
  analytics:  "Analytics",
  settings:   "Settings",
  new:        "New Campaign",
};

function prettify(s: string) {
  return LABELS[s] ?? s.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function Header() {
  const path     = useRouterState({ select: (s) => s.location.pathname });
  const segments = path.split("/").filter(Boolean);

  return (
    <header className="sticky top-0 z-40 h-14 bg-background/90 backdrop-blur-md border-b border-border/60 flex items-center px-6 gap-4">

      {/* Breadcrumb */}
      <nav className="flex items-center gap-1 text-sm min-w-0">
        {segments.map((s, i) => {
          const isLast = i === segments.length - 1;
          return (
            <span key={i} className="flex items-center gap-1 min-w-0">
              {i > 0 && (
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/40 shrink-0" />
              )}
              <span
                className={`truncate ${
                  isLast
                    ? "text-foreground font-semibold"
                    : "text-muted-foreground hover:text-foreground transition-colors"
                }`}
              >
                {prettify(s)}
              </span>
            </span>
          );
        })}
      </nav>

      {/* Search */}
      <div className="flex-1 max-w-xs mx-auto relative hidden sm:block">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/50 pointer-events-none" />
        <input
          placeholder="Search…"
          className="w-full pl-9 pr-3 h-8 rounded-lg bg-surface-2 border border-border/60 text-sm placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 transition-all"
        />
      </div>

      {/* Right actions */}
      <div className="flex items-center gap-2 ml-auto">

        {/* Notification bell */}
        <button className="relative h-8 w-8 grid place-items-center rounded-lg hover:bg-surface-2 text-muted-foreground hover:text-foreground transition-colors">
          <Bell className="h-4 w-4" />
          <span className="absolute top-1.5 right-1.5 h-1.5 w-1.5 rounded-full bg-primary ring-2 ring-background" />
        </button>

        {/* New Campaign */}
        <Link to="/campaigns/new">
          <Button
            size="sm"
            className="h-8 bg-gradient-primary text-primary-foreground shadow-glow hover:opacity-90 gap-1.5 text-xs font-semibold px-3"
          >
            <Plus className="h-3.5 w-3.5" />
            New Campaign
          </Button>
        </Link>
      </div>
    </header>
  );
}
