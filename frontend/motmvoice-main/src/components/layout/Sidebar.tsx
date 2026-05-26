import { Link, useRouterState, useNavigate } from "@tanstack/react-router";
import {
  Mic, LayoutDashboard, Megaphone, Phone,
  Bot, BarChart3, Settings, LogOut, Zap,
} from "lucide-react";
import { useAuth } from "@/lib/auth";

// ── Navigation items ─────────────────────────────────────────────────────────
const mainNav = [
  { to: "/dashboard",  label: "Dashboard",    icon: LayoutDashboard },
  { to: "/campaigns",  label: "Campaigns",    icon: Megaphone       },
  { to: "/calls",      label: "Call History", icon: Phone           },
  { to: "/agents",     label: "AI Agents",    icon: Bot             },
  { to: "/analytics",  label: "Analytics",    icon: BarChart3       },
] as const;

const bottomNav = [
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

// ── Nav link ─────────────────────────────────────────────────────────────────
function NavLink({
  to, label, icon: Icon, path,
}: {
  to: string; label: string; icon: React.ElementType; path: string;
}) {
  const active = path === to || (to !== "/dashboard" && path.startsWith(to));
  return (
    <Link
      to={to}
      className={`group relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] font-medium transition-all duration-150 ${
        active
          ? "bg-primary/12 text-foreground"
          : "text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
      }`}
    >
      {/* Left accent pill */}
      <span
        className={`absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-full transition-all duration-200 ${
          active
            ? "bg-primary opacity-100 shadow-glow"
            : "bg-primary opacity-0 group-hover:opacity-25"
        }`}
      />
      <Icon
        className={`h-[15px] w-[15px] shrink-0 transition-colors ${
          active ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
        }`}
      />
      <span>{label}</span>
      {active && (
        <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary opacity-80" />
      )}
    </Link>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
export function Sidebar() {
  const path              = useRouterState({ select: (s) => s.location.pathname });
  const { user, logout }  = useAuth();
  const navigate          = useNavigate();
  const initials          = user?.full_name
    ? user.full_name.split(" ").map((n) => n[0]).slice(0, 2).join("").toUpperCase()
    : "U";

  return (
    <aside className="hidden md:flex flex-col w-[220px] shrink-0 bg-sidebar border-r border-sidebar-border h-screen sticky top-0 overflow-hidden">

      {/* ── Subtle background texture ─────────────────────────────────────── */}
      <div className="absolute inset-0 dot-grid opacity-[0.08] pointer-events-none" />
      {/* Soft orange radial glow at top-right */}
      <div className="absolute -top-16 -right-16 w-48 h-48 rounded-full bg-primary/6 blur-3xl pointer-events-none" />

      {/* ── Logo ──────────────────────────────────────────────────────────── */}
      <Link
        to="/dashboard"
        className="relative flex items-center gap-3 px-5 h-[60px] border-b border-sidebar-border shrink-0 group"
      >
        {/* Icon cube */}
        <div className="h-8 w-8 rounded-lg bg-gradient-primary grid place-items-center shadow-glow shrink-0 float-glow">
          <Mic className="h-4 w-4 text-white" />
        </div>
        <div className="min-w-0">
          <div className="font-bold text-[14px] tracking-tight leading-none text-foreground">
            MOTMVoice
          </div>
          <div className="flex items-center gap-1 mt-0.5">
            <Zap className="h-2.5 w-2.5 text-primary" />
            <span className="text-[10px] text-primary font-medium tracking-wide">
              AI Voice Platform
            </span>
          </div>
        </div>
      </Link>

      {/* ── Main nav ──────────────────────────────────────────────────────── */}
      <nav className="relative flex-1 flex flex-col px-2.5 py-4 overflow-y-auto">

        {/* MENU section */}
        <p className="px-3 mb-2 text-[9px] font-bold tracking-[0.12em] uppercase text-muted-foreground/40 select-none">
          Menu
        </p>
        <div className="space-y-0.5">
          {mainNav.map((it) => (
            <NavLink key={it.to} to={it.to} label={it.label} icon={it.icon} path={path} />
          ))}
        </div>

        {/* Divider */}
        <div className="my-4 mx-3 border-t border-sidebar-border/50" />

        {/* ACCOUNT section */}
        <p className="px-3 mb-2 text-[9px] font-bold tracking-[0.12em] uppercase text-muted-foreground/40 select-none">
          Account
        </p>
        <div className="space-y-0.5">
          {bottomNav.map((it) => (
            <NavLink key={it.to} to={it.to} label={it.label} icon={it.icon} path={path} />
          ))}
        </div>
      </nav>

      {/* ── User card ─────────────────────────────────────────────────────── */}
      <div className="relative px-2.5 pb-3 pt-2 border-t border-sidebar-border shrink-0">
        <div className="flex items-center gap-2.5 px-2 py-2.5 rounded-lg hover:bg-sidebar-accent transition-colors">

          {/* Avatar */}
          <div className="h-7 w-7 rounded-full bg-gradient-primary grid place-items-center text-white text-[11px] font-bold shrink-0 shadow-glow">
            {initials}
          </div>

          {/* Name + badge */}
          <div className="min-w-0 flex-1">
            <div className="text-[12px] font-semibold truncate leading-tight text-foreground">
              {user?.full_name ?? "Guest"}
            </div>
            <div className="flex items-center gap-1 mt-0.5">
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-primary/15 text-primary font-bold leading-none tracking-wide uppercase">
                PRO
              </span>
              <span className="text-[11px] text-muted-foreground/70 capitalize truncate">
                {user?.role ?? "member"}
              </span>
            </div>
          </div>

          {/* Logout */}
          <button
            onClick={() => { logout(); navigate({ to: "/login" }); }}
            title="Sign out"
            className="text-muted-foreground/50 hover:text-foreground transition-colors shrink-0 p-1 rounded-md hover:bg-sidebar-accent"
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

    </aside>
  );
}
