import { Link, useRouterState, useNavigate } from "@tanstack/react-router";
import {
  Mic, LayoutDashboard, Megaphone, Phone,
  Bot, BarChart3, Settings, LogOut, Zap,
} from "lucide-react";
import { useAuth } from "@/lib/auth";

// ── Nav config ───────────────────────────────────────────────────────────────
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
  to, label, icon: Icon, path, delay = 0,
}: {
  to: string; label: string; icon: React.ElementType; path: string; delay?: number;
}) {
  const active = path === to || (to !== "/dashboard" && path.startsWith(to));

  return (
    <Link
      to={to}
      className="group relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-200 animate-slide-in"
      style={{
        animationDelay: `${delay}ms`,
        ...(active
          ? {
              backgroundImage: "var(--gradient-primary)",
              color: "oklch(0.990 0.003 280)",
              boxShadow: "0 4px 20px oklch(0.565 0.240 284 / 0.30), inset 0 1px 0 oklch(1 0 0 / 0.10)",
            }
          : {
              color: "var(--muted-foreground)",
            }),
      }}
    >
      {/* Hover background — only shown when not active */}
      {!active && (
        <span className="absolute inset-0 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-150"
          style={{ background: "var(--sidebar-accent)" }}
        />
      )}

      <Icon
        className="relative z-10 shrink-0 transition-all duration-200"
        style={{
          width: "15px", height: "15px",
          color: active ? "oklch(0.990 0.003 280)" : undefined,
          filter: active ? "drop-shadow(0 0 6px oklch(0.90 0.10 280 / 0.6))" : undefined,
        }}
      />

      <span className="relative z-10 tracking-tight">{label}</span>

      {/* Active glow indicator dot */}
      {active && (
        <span
          className="relative z-10 ml-auto h-1.5 w-1.5 rounded-full"
          style={{ background: "oklch(0.90 0.08 280)", boxShadow: "0 0 6px oklch(0.90 0.10 280)" }}
        />
      )}

      {/* Hover text colour shift */}
      {!active && (
        <style>{`
          [href="${to}"]:hover span { color: var(--foreground); }
        `}</style>
      )}
    </Link>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
export function Sidebar() {
  const path             = useRouterState({ select: (s) => s.location.pathname });
  const { user, logout } = useAuth();
  const navigate         = useNavigate();
  const initials         = user?.full_name
    ? user.full_name.split(" ").map((n: string) => n[0]).slice(0, 2).join("").toUpperCase()
    : "U";

  return (
    <aside
      className="hidden md:flex flex-col w-[220px] shrink-0 h-screen sticky top-0 overflow-hidden animate-slide-in"
      style={{
        background: "var(--sidebar)",
        borderRight: "1px solid var(--sidebar-border)",
      }}
    >

      {/* ── Noise/dot-grid background texture ─────────────────────────────── */}
      <div className="absolute inset-0 dot-grid opacity-[0.06] pointer-events-none" />

      {/* ── Subtle purple radial glow (top-left) ─────────────────────────── */}
      <div
        className="absolute pointer-events-none"
        style={{
          top: "-60px", left: "-40px",
          width: "220px", height: "220px",
          background: "radial-gradient(circle, oklch(0.565 0.240 284 / 0.12) 0%, transparent 70%)",
        }}
      />

      {/* ── Logo ──────────────────────────────────────────────────────────── */}
      <Link
        to="/dashboard"
        className="relative flex items-center gap-3 px-5 h-[60px] shrink-0"
        style={{ borderBottom: "1px solid var(--sidebar-border)" }}
      >
        {/* Gradient icon cube with floating glow */}
        <div
          className="h-8 w-8 rounded-lg grid place-items-center shrink-0 float-glow"
          style={{
            backgroundImage: "var(--gradient-primary)",
            boxShadow: "0 0 20px oklch(0.565 0.240 284 / 0.45), 0 0 8px oklch(0.565 0.240 284 / 0.25)",
          }}
        >
          <Mic className="h-4 w-4" style={{ color: "oklch(0.990 0.003 280)", filter: "drop-shadow(0 0 4px oklch(1 0 0 / 0.4))" }} />
        </div>

        {/* Name + sub-label */}
        <div className="min-w-0">
          <div className="font-bold text-[14px] tracking-tight leading-none text-foreground">
            MOTMVoice
          </div>
          <div className="flex items-center gap-1 mt-0.5">
            <Zap className="h-2.5 w-2.5" style={{ color: "oklch(0.70 0.18 284)" }} />
            <span
              className="text-[10px] font-semibold tracking-wide"
              style={{ color: "oklch(0.70 0.18 284)" }}
            >
              AI Voice Platform
            </span>
          </div>
        </div>
      </Link>

      {/* ── Nav ───────────────────────────────────────────────────────────── */}
      <nav className="relative flex-1 flex flex-col px-2.5 py-4 overflow-y-auto">

        {/* MENU */}
        <p className="px-3 mb-2 text-[9px] font-bold tracking-[0.12em] uppercase select-none"
          style={{ color: "var(--muted-foreground)" }}>
          Menu
        </p>
        <div className="space-y-0.5">
          {mainNav.map((it, i) => (
            <NavLink key={it.to} to={it.to} label={it.label} icon={it.icon} path={path} delay={i * 40} />
          ))}
        </div>

        {/* Divider */}
        <div className="my-4 mx-3" style={{ borderTop: "1px solid var(--sidebar-border)" }} />

        {/* ACCOUNT */}
        <p className="px-3 mb-2 text-[9px] font-bold tracking-[0.12em] uppercase select-none"
          style={{ color: "var(--muted-foreground)" }}>
          Account
        </p>
        <div className="space-y-0.5">
          {bottomNav.map((it, i) => (
            <NavLink key={it.to} to={it.to} label={it.label} icon={it.icon} path={path} delay={(mainNav.length + 1 + i) * 40} />
          ))}
        </div>
      </nav>

      {/* ── User card — glassmorphism ──────────────────────────────────────── */}
      <div className="px-2.5 pb-3 pt-2 shrink-0" style={{ borderTop: "1px solid var(--sidebar-border)" }}>
        <div
          className="glass-card flex items-center gap-2.5 px-3 py-2.5 rounded-xl transition-all duration-200 hover:shadow-glow cursor-default"
        >
          {/* Gradient avatar */}
          <div
            className="h-7 w-7 rounded-full grid place-items-center text-[11px] font-bold shrink-0"
            style={{
              backgroundImage: "var(--gradient-primary)",
              color: "oklch(0.990 0.003 280)",
              boxShadow: "0 0 12px oklch(0.565 0.240 284 / 0.40)",
            }}
          >
            {initials}
          </div>

          {/* Name + role */}
          <div className="min-w-0 flex-1">
            <div className="text-[12px] font-semibold truncate leading-tight text-foreground">
              {user?.full_name ?? "Guest"}
            </div>
            <div className="flex items-center gap-1 mt-0.5">
              <span
                className="text-[9px] px-1.5 py-0.5 rounded font-bold leading-none tracking-wide uppercase"
                style={{
                  backgroundImage: "var(--gradient-primary)",
                  color: "oklch(0.990 0.003 280)",
                }}
              >
                PRO
              </span>
              <span className="text-[11px] capitalize truncate text-muted-foreground">
                {user?.role ?? "member"}
              </span>
            </div>
          </div>

          {/* Logout */}
          <button
            onClick={() => { logout(); navigate({ to: "/login" }); }}
            title="Sign out"
            className="text-muted-foreground hover:text-foreground transition-all duration-150 shrink-0 p-1 rounded-md hover:bg-sidebar-accent"
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

    </aside>
  );
}
