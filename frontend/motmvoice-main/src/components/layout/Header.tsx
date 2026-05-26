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
      className="sticky top-0 z-40 h-14 flex items-center px-6 gap-4 animate-fade-up"
      style={{
        background: "oklch(0.065 0.008 270 / 0.85)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderBottom: "1px solid oklch(0.165 0.015 270 / 0.70)",
      }}
    >

      {/* ── Breadcrumb ────────────────────────────────────────────────────── */}
      <nav className="flex items-center gap-1 text-sm min-w-0">
        {segments.map((s, i) => {
          const isLast = i === segments.length - 1;
          return (
            <span key={i} className="flex items-center gap-1 min-w-0">
              {i > 0 && (
                <ChevronRight
                  className="h-3.5 w-3.5 shrink-0"
                  style={{ color: "oklch(0.35 0.010 270)" }}
                />
              )}
              <span
                className="truncate font-medium transition-colors duration-150"
                style={{
                  color: isLast
                    ? "oklch(0.950 0.008 280)"
                    : "oklch(0.50 0.012 270)",
                  ...(isLast && {
                    filter: "drop-shadow(0 0 8px oklch(0.565 0.240 284 / 0.30))",
                  }),
                }}
              >
                {prettify(s)}
              </span>
            </span>
          );
        })}
      </nav>

      {/* ── Search ────────────────────────────────────────────────────────── */}
      <div className="flex-1 max-w-xs mx-auto relative hidden sm:block">
        <Search
          className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 pointer-events-none"
          style={{ color: "oklch(0.45 0.010 270)" }}
        />
        <input
          placeholder="Search…"
          className="w-full pl-9 pr-3 h-8 rounded-lg text-sm transition-all duration-200 focus:outline-none"
          style={{
            background: "oklch(0.105 0.012 270 / 0.80)",
            border: "1px solid oklch(0.165 0.015 270)",
            color: "oklch(0.950 0.008 280)",
            /* focus state handled by CSS below */
          }}
          onFocus={(e) => {
            e.currentTarget.style.border = "1px solid oklch(0.565 0.240 284 / 0.70)";
            e.currentTarget.style.boxShadow = "0 0 0 3px oklch(0.565 0.240 284 / 0.15), 0 0 12px oklch(0.565 0.240 284 / 0.10)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.border = "1px solid oklch(0.165 0.015 270)";
            e.currentTarget.style.boxShadow = "none";
          }}
        />
      </div>

      {/* ── Right actions ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 ml-auto">

        {/* Notification bell */}
        <button
          className="relative h-8 w-8 grid place-items-center rounded-lg transition-all duration-150"
          style={{ color: "oklch(0.50 0.012 270)" }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "oklch(0.130 0.013 270)";
            e.currentTarget.style.color = "oklch(0.950 0.008 280)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.color = "oklch(0.50 0.012 270)";
          }}
        >
          <Bell className="h-4 w-4" />
          {/* Animated pulse dot */}
          <span
            className="absolute top-1.5 right-1.5 h-1.5 w-1.5 rounded-full pulse-dot"
            style={{ background: "oklch(0.565 0.240 284)", boxShadow: "0 0 6px oklch(0.565 0.240 284)" }}
          />
        </button>

        {/* New Campaign — gradient + hover glow */}
        <Link to="/campaigns/new">
          <Button
            size="sm"
            className="h-8 gap-1.5 text-xs font-semibold px-3 transition-all duration-200"
            style={{
              backgroundImage: "var(--gradient-primary)",
              color: "oklch(0.990 0.003 280)",
              border: "none",
              boxShadow: "0 4px 14px oklch(0.565 0.240 284 / 0.30)",
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
