import { Link, useRouterState } from "@tanstack/react-router";
import { Bell, Plus, Search, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

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
    <header
      className="sticky top-0 z-40 h-14 flex items-center px-6 gap-4 animate-fade-up bg-card border-b border-border"
    >

      {/* ── Breadcrumb ────────────────────────────────────────────────────── */}
      <nav className="flex items-center gap-1 text-sm min-w-0">
        {segments.map((s, i) => {
          const isLast = i === segments.length - 1;
          return (
            <span key={i} className="flex items-center gap-1 min-w-0">
              {i > 0 && (
                <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
              )}
              <span
                className={`truncate font-medium transition-colors duration-150 ${
                  isLast ? "text-foreground" : "text-muted-foreground"
                }`}
              >
                {prettify(s)}
              </span>
            </span>
          );
        })}
      </nav>

      {/* ── Search ────────────────────────────────────────────────────────── */}
      <div className="flex-1 max-w-xs mx-auto relative hidden sm:block">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 pointer-events-none text-muted-foreground/50" />
        <input
          placeholder="Search…"
          className="w-full pl-9 pr-3 h-8 rounded-lg text-sm transition-all duration-200 focus:outline-none"
          style={{
            background: "var(--input)",
            border:     "1px solid var(--border)",
            color:      "var(--foreground)",
          }}
          onFocus={(e) => {
            e.currentTarget.style.border    = "1px solid var(--ring)";
            e.currentTarget.style.boxShadow = "0 0 0 3px color-mix(in oklch, var(--ring) 15%, transparent)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.border    = "1px solid var(--border)";
            e.currentTarget.style.boxShadow = "none";
          }}
        />
      </div>

      {/* ── Right actions ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 ml-auto">

        {/* Notification bell */}
        <button
          className="relative h-8 w-8 grid place-items-center rounded-lg transition-all duration-150 text-muted-foreground hover:text-foreground hover:bg-accent"
        >
          <Bell className="h-4 w-4" />
          <span
            className="absolute top-1.5 right-1.5 h-1.5 w-1.5 rounded-full pulse-dot"
            style={{ background: "var(--primary)", boxShadow: "0 0 6px var(--primary)" }}
          />
        </button>

        {/* New Campaign — gradient + hover glow */}
        <Link to="/campaigns/new">
          <Button
            size="sm"
            className="h-8 gap-1.5 text-xs font-semibold px-3 transition-all duration-200 border-none"
            style={{
              backgroundImage: "var(--gradient-primary)",
              color:           "oklch(0.990 0.003 280)",
              boxShadow:       "0 4px 14px oklch(0.565 0.240 284 / 0.30)",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.boxShadow = "0 6px 20px oklch(0.565 0.240 284 / 0.50)";
              e.currentTarget.style.transform = "scale(1.02)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.boxShadow = "0 4px 14px oklch(0.565 0.240 284 / 0.30)";
              e.currentTarget.style.transform = "scale(1)";
            }}
          >
            <Plus className="h-3.5 w-3.5" />
            New Campaign
          </Button>
        </Link>
      </div>
    </header>
  );
}
