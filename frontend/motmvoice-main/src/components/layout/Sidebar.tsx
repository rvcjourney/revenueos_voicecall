import { Link, useRouterState, useNavigate } from "@tanstack/react-router";
import {
  LayoutDashboard, Megaphone, Phone,
  Bot, BarChart3, Settings, LogOut, Zap, Users, Shield, PhoneOff, ClipboardList,
  Bell, CheckCircle, Clock, Play, X, Loader2,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { LogoMark } from "@/components/Logo";
import { adminApi, campaignsApi, type ActivityEvent, type CampaignOut } from "@/lib/api";
import { useState, useEffect, useRef } from "react";

// ── Notification helpers ──────────────────────────────────────────────────────
interface NotifItem {
  id: string;
  icon: React.ElementType;
  iconColor: string;
  title: string;
  body: string;
  timestamp: string;
}

function activityToNotif(e: ActivityEvent, idx: number): NotifItem {
  const map: Record<string, { icon: React.ElementType; color: string }> = {
    campaign_created:       { icon: Megaphone,   color: "text-primary"            },
    campaign_launched:      { icon: Play,        color: "text-success"            },
    campaign_completed:     { icon: CheckCircle, color: "text-success"            },
    agent_access_approved:  { icon: Bot,         color: "text-primary"            },
    agent_access_pending:   { icon: Clock,       color: "text-amber-400"          },
    agent_access_rejected:  { icon: X,           color: "text-destructive"        },
  };
  const meta = map[e.type] ?? { icon: Megaphone, color: "text-muted-foreground" };
  return {
    id: `${e.timestamp}-${idx}`,
    icon: meta.icon,
    iconColor: meta.color,
    title: e.type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    body: `${e.user_name} — ${e.detail}`,
    timestamp: e.timestamp,
  };
}

function campaignToNotif(c: CampaignOut): NotifItem {
  const map: Record<string, { icon: React.ElementType; color: string; body: string }> = {
    running:   { icon: Play,        color: "text-primary",          body: `${c.completed_calls}/${c.total_contacts} calls done` },
    completed: { icon: CheckCircle, color: "text-success",          body: `Finished — ${c.interested_count} interested`         },
    scheduled: { icon: Clock,       color: "text-amber-400",        body: `Scheduled for ${c.start_time ? new Date(c.start_time).toLocaleString() : "—"}` },
    paused:    { icon: Megaphone,   color: "text-muted-foreground", body: "Campaign is paused"                                  },
  };
  const meta = map[c.status] ?? { icon: Megaphone, color: "text-muted-foreground", body: c.status };
  return { id: c.id, icon: meta.icon, iconColor: meta.color, title: c.name, body: meta.body, timestamp: c.started_at ?? c.created_at };
}

function formatAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60)  return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60)  return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// ── Notification Bell ─────────────────────────────────────────────────────────
function NotificationBell({ isAdmin }: { isAdmin: boolean }) {
  const [open, setOpen]       = useState(false);
  const [items, setItems]     = useState<NotifItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasNew, setHasNew]   = useState(true);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const seen = parseInt(localStorage.getItem("motm_notif_seen") ?? "0", 10);
    if (Date.now() - seen < 60 * 60 * 1000) setHasNew(false);
  }, []);

  useEffect(() => {
    if (!open) return;
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [open]);

  async function toggleOpen() {
    if (open) { setOpen(false); return; }
    setOpen(true);
    setLoading(true);
    try {
      if (isAdmin) {
        const { data } = await adminApi.getActivity();
        setItems(data.slice(0, 12).map((e, i) => activityToNotif(e, i)));
      } else {
        const { data } = await campaignsApi.list();
        setItems(
          (data.items ?? [])
            .filter((c) => ["running", "completed", "scheduled", "paused"].includes(c.status))
            .slice(0, 12)
            .map(campaignToNotif)
        );
      }
      localStorage.setItem("motm_notif_seen", String(Date.now()));
      setHasNew(false);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={toggleOpen}
        title="Notifications"
        className="relative p-1 rounded-md text-muted-foreground hover:text-foreground transition-all duration-150 hover:bg-sidebar-accent"
      >
        <Bell className="h-3.5 w-3.5" />
        {hasNew && (
          <span
            className="absolute top-0.5 right-0.5 h-1.5 w-1.5 rounded-full"
            style={{ background: "var(--primary)", boxShadow: "0 0 5px var(--primary)" }}
          />
        )}
      </button>

      {open && (
        <div className="absolute left-full bottom-0 ml-2 z-50 w-72 rounded-xl bg-card border border-border shadow-xl overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-border">
            <span className="text-sm font-semibold">Notifications</span>
            <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="max-h-72 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : items.length === 0 ? (
              <div className="py-8 text-center">
                <Bell className="h-7 w-7 mx-auto text-muted-foreground/30 mb-2" />
                <p className="text-xs text-muted-foreground">No recent activity</p>
              </div>
            ) : (
              <ul>
                {items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <li key={item.id} className="flex items-start gap-3 px-4 py-2.5 border-b border-border/50 last:border-0 hover:bg-surface-2/40 transition-colors">
                      <span className={`mt-0.5 shrink-0 ${item.iconColor}`}>
                        <Icon className="h-3.5 w-3.5" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-semibold truncate">{item.title}</p>
                        <p className="text-[11px] text-muted-foreground truncate">{item.body}</p>
                      </div>
                      <span className="text-[10px] text-muted-foreground shrink-0 mt-0.5">{formatAgo(item.timestamp)}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── NavLink ───────────────────────────────────────────────────────────────────
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
          : { color: "var(--muted-foreground)" }),
      }}
    >
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
      {active && (
        <span
          className="relative z-10 ml-auto h-1.5 w-1.5 rounded-full"
          style={{ background: "oklch(0.90 0.08 280)", boxShadow: "0 0 6px oklch(0.90 0.10 280)" }}
        />
      )}
      {!active && (
        <style>{`[href="${to}"]:hover span { color: var(--foreground); }`}</style>
      )}
    </Link>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
export function Sidebar() {
  const path             = useRouterState({ select: (s) => s.location.pathname });
  const { user, isAdmin, logout } = useAuth();
  const navigate         = useNavigate();
  const initials         = user?.full_name
    ? user.full_name.split(" ").map((n: string) => n[0]).slice(0, 2).join("").toUpperCase()
    : "U";

  const commonNav = [
    { to: "/dashboard",  label: "Dashboard",    icon: LayoutDashboard },
    { to: "/campaigns",  label: "Campaigns",    icon: Megaphone       },
    { to: "/calls",      label: "Call History", icon: Phone           },
    { to: "/analytics",  label: "Analytics",    icon: BarChart3       },
  ] as const;

  const adminNav = [
    { to: "/agents",      label: "AI Agents",  icon: Bot             },
    { to: "/admin/users", label: "Team",        icon: Users           },
    { to: "/admin/dnc",   label: "DNC List",   icon: PhoneOff        },
    { to: "/admin/audit", label: "Audit Log",  icon: ClipboardList   },
    { to: "/settings",    label: "Settings",   icon: Settings        },
  ] as const;

  const memberNav = [
    { to: "/agents",     label: "AI Agents",    icon: Bot             },
  ] as const;

  return (
    <aside
      className="hidden md:flex flex-col w-[220px] shrink-0 h-screen sticky top-0 overflow-hidden animate-slide-in"
      style={{
        background: "var(--sidebar)",
        borderRight: "1px solid var(--sidebar-border)",
      }}
    >
      <div className="absolute inset-0 dot-grid opacity-[0.06] pointer-events-none" />
      <div
        className="absolute pointer-events-none"
        style={{
          top: "-60px", left: "-40px",
          width: "220px", height: "220px",
          background: "radial-gradient(circle, oklch(0.565 0.240 284 / 0.12) 0%, transparent 70%)",
        }}
      />

      {/* Logo */}
      <Link
        to="/dashboard"
        className="relative flex items-center gap-3 px-4 h-[62px] shrink-0"
        style={{ borderBottom: "1px solid var(--sidebar-border)" }}
      >
        <div className="shrink-0 float-glow" style={{ filter: "drop-shadow(0 0 10px oklch(0.55 0.24 278 / 0.55))" }}>
          <LogoMark size={36} />
        </div>
        <div className="min-w-0">
          <div
            className="font-bold text-[14px] tracking-tight leading-none"
            style={{
              background: "linear-gradient(135deg, #fff 30%, oklch(0.78 0.18 268))",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}
          >
            MOTM<span style={{ fontWeight: 300 }}>Voice</span>
          </div>
          <div className="flex items-center gap-1 mt-0.5">
            <Zap className="h-2.5 w-2.5" style={{ color: "oklch(0.70 0.18 284)" }} />
            <span className="text-[10px] font-semibold tracking-wide" style={{ color: "oklch(0.68 0.16 270)" }}>
              AI Voice Platform
            </span>
          </div>
        </div>
      </Link>

      {/* Nav */}
      <nav className="relative flex-1 flex flex-col px-2.5 py-4 overflow-y-auto">
        <p className="px-3 mb-2 text-[9px] font-bold tracking-[0.12em] uppercase select-none"
          style={{ color: "var(--muted-foreground)" }}>
          Menu
        </p>
        <div className="space-y-0.5">
          {commonNav.map((it, i) => (
            <NavLink key={it.to} to={it.to} label={it.label} icon={it.icon} path={path} delay={i * 40} />
          ))}
          {!isAdmin && memberNav.map((it, i) => (
            <NavLink key={it.to} to={it.to} label={it.label} icon={it.icon} path={path} delay={(commonNav.length + i) * 40} />
          ))}
        </div>

        {isAdmin && (
          <>
            <div className="my-4 mx-3" style={{ borderTop: "1px solid var(--sidebar-border)" }} />
            <p className="px-3 mb-2 text-[9px] font-bold tracking-[0.12em] uppercase select-none"
              style={{ color: "var(--muted-foreground)" }}>
              Admin
            </p>
            <div className="space-y-0.5">
              {adminNav.map((it, i) => (
                <NavLink key={it.to} to={it.to} label={it.label} icon={it.icon} path={path} delay={(commonNav.length + 1 + i) * 40} />
              ))}
            </div>
          </>
        )}
      </nav>

      {/* User card */}
      <div className="px-2.5 pb-3 pt-2 shrink-0" style={{ borderTop: "1px solid var(--sidebar-border)" }}>
        <div className="glass-card flex items-center gap-2.5 px-3 py-2.5 rounded-xl transition-all duration-200 hover:shadow-glow cursor-default">
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
          <div className="min-w-0 flex-1">
            <div className="text-[12px] font-semibold truncate leading-tight text-foreground">
              {user?.full_name ?? "Guest"}
            </div>
            <div className="flex items-center gap-1 mt-0.5">
              {isAdmin ? (
                <span className="inline-flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded font-bold leading-none tracking-wide uppercase"
                  style={{ backgroundImage: "var(--gradient-primary)", color: "oklch(0.990 0.003 280)" }}>
                  <Shield className="h-2 w-2" /> Admin
                </span>
              ) : (
                <span className="text-[9px] px-1.5 py-0.5 rounded font-bold leading-none tracking-wide uppercase border border-border text-muted-foreground">
                  Member
                </span>
              )}
            </div>
          </div>
          {/* Bell notification */}
          <NotificationBell isAdmin={isAdmin} />
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
