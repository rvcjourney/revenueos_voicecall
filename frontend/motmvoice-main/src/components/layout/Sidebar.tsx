import { Link, useRouterState, useNavigate } from "@tanstack/react-router";
import {
  Mic, LayoutDashboard, Megaphone, Phone,
  Bot, BarChart3, Settings, LogOut,
} from "lucide-react";
import { useAuth } from "@/lib/auth";

// ── Main navigation items ────────────────────────────────────────────────────
const mainNav = [
  { to: "/dashboard",  label: "Dashboard",   icon: LayoutDashboard },
  { to: "/campaigns",  label: "Campaigns",   icon: Megaphone       },
  { to: "/calls",      label: "Call History", icon: Phone          },
  { to: "/agents",     label: "AI Agents",   icon: Bot             },
  { to: "/analytics",  label: "Analytics",   icon: BarChart3       },
] as const;

// ── Bottom / system items ────────────────────────────────────────────────────
const bottomNav = [
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

// ── Nav link helper ──────────────────────────────────────────────────────────
function NavLink({
  to, label, icon: Icon, path,
}: {
  to: string; label: string; icon: React.ElementType; path: string;
}) {
  const active = path === to || (to !== "/dashboard" && path.startsWith(to));
  return (
    <Link
      to={to}
      className={`group flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
        active
          ? "bg-primary/10 text-foreground"
          : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground"
      }`}
    >
      {/* Left accent bar */}
      <span
        className={`absolute left-0 top-1/2 -translate-y-1/2 h-5 w-0.5 rounded-full bg-primary transition-opacity ${
          active ? "opacity-100" : "opacity-0 group-hover:opacity-30"
        }`}
      />
      <Icon className={`h-4 w-4 shrink-0 ${active ? "text-primary" : ""}`} />
      {label}
    </Link>
  );
}

export function Sidebar() {
  const path     = useRouterState({ select: (s) => s.location.pathname });
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <aside className="hidden md:flex flex-col w-60 shrink-0 bg-sidebar border-r border-sidebar-border h-screen sticky top-0">

      {/* ── Logo ──────────────────────────────────────────────────────────── */}
      <Link
        to="/dashboard"
        className="flex items-center gap-2.5 px-5 h-16 border-b border-sidebar-border shrink-0"
      >
        <div className="h-8 w-8 rounded-lg bg-gradient-primary grid place-items-center shadow-glow shrink-0">
          <Mic className="h-4 w-4 text-white" />
        </div>
        <span className="font-bold tracking-tight text-[15px]">MOTMVoice</span>
      </Link>

      {/* ── Main nav ──────────────────────────────────────────────────────── */}
      <nav className="flex-1 flex flex-col px-3 py-4 overflow-y-auto gap-0.5">
        <p className="px-3 text-[10px] font-semibold tracking-widest uppercase text-muted-foreground/50 mb-1.5">
          Menu
        </p>
        {mainNav.map((it) => (
          <div key={it.to} className="relative">
            <NavLink to={it.to} label={it.label} icon={it.icon} path={path} />
          </div>
        ))}

        {/* Divider */}
        <div className="my-3 border-t border-sidebar-border/60" />

        <p className="px-3 text-[10px] font-semibold tracking-widest uppercase text-muted-foreground/50 mb-1.5">
          Account
        </p>
        {bottomNav.map((it) => (
          <div key={it.to} className="relative">
            <NavLink to={it.to} label={it.label} icon={it.icon} path={path} />
          </div>
        ))}
      </nav>

      {/* ── User card ─────────────────────────────────────────────────────── */}
      <div className="p-3 border-t border-sidebar-border shrink-0">
        <div className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-sidebar-accent/40 transition-colors">
          {/* Avatar */}
          <div className="h-8 w-8 rounded-full bg-gradient-primary grid place-items-center text-white text-sm font-semibold shrink-0">
            {user?.full_name?.[0]?.toUpperCase() ?? "U"}
          </div>

          {/* Name + role */}
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium truncate leading-tight">
              {user?.full_name ?? "Guest"}
            </div>
            <div className="flex items-center gap-1 mt-0.5">
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/15 text-primary font-semibold leading-none">
                PRO
              </span>
              <span className="text-[11px] text-muted-foreground capitalize truncate">
                {user?.role ?? "member"}
              </span>
            </div>
          </div>

          {/* Logout */}
          <button
            onClick={() => { logout(); navigate({ to: "/login" }); }}
            title="Sign out"
            className="text-muted-foreground hover:text-foreground transition-colors shrink-0 p-1 rounded hover:bg-sidebar-accent"
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
}
