import { Link, useRouterState } from "@tanstack/react-router";
import { Bell, Plus, Search, ChevronRight, Megaphone, Bot, CheckCircle, Clock, Play, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { adminApi, campaignsApi, type ActivityEvent, type CampaignOut } from "@/lib/api";
import { useState, useEffect, useRef } from "react";

const LABELS: Record<string, string> = {
  dashboard:  "Dashboard",
  campaigns:  "Campaigns",
  calls:      "Call History",
  agents:     "AI Agents",
  analytics:  "Analytics",
  settings:   "Settings",
  new:        "New Campaign",
  admin:      "Admin",
  users:      "Team",
  dnc:        "DNC List",
  audit:      "Audit Log",
};

function prettify(s: string) {
  return LABELS[s] ?? s.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Notification types ────────────────────────────────────────────────────────
interface NotifItem {
  id: string;
  icon: React.ElementType;
  iconColor: string;
  title: string;
  body: string;
  timestamp: string;
}

function activityToNotif(e: ActivityEvent, idx: number): NotifItem {
  const iconMap: Record<string, { icon: React.ElementType; color: string }> = {
    campaign_created:       { icon: Megaphone,    color: "text-primary"        },
    campaign_launched:      { icon: Play,         color: "text-success"        },
    campaign_completed:     { icon: CheckCircle,  color: "text-success"        },
    agent_access_approved:  { icon: Bot,          color: "text-primary"        },
    agent_access_pending:   { icon: Clock,        color: "text-amber-400"      },
    agent_access_rejected:  { icon: X,            color: "text-destructive"    },
  };
  const meta = iconMap[e.type] ?? { icon: Megaphone, color: "text-muted-foreground" };
  const label = e.type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return {
    id: `${e.timestamp}-${idx}`,
    icon: meta.icon,
    iconColor: meta.color,
    title: label,
    body: `${e.user_name} — ${e.detail}`,
    timestamp: e.timestamp,
  };
}

function campaignToNotif(c: CampaignOut): NotifItem {
  const statusMap: Record<string, { icon: React.ElementType; color: string; body: string }> = {
    running:   { icon: Play,        color: "text-primary",   body: `${c.completed_calls}/${c.total_contacts} calls completed` },
    completed: { icon: CheckCircle, color: "text-success",   body: `Finished — ${c.interested_count} interested leads`       },
    scheduled: { icon: Clock,       color: "text-amber-400", body: `Scheduled for ${c.start_time ? new Date(c.start_time).toLocaleString() : "—"}` },
    paused:    { icon: Megaphone,   color: "text-muted-foreground", body: "Campaign is paused"                              },
  };
  const meta = statusMap[c.status] ?? { icon: Megaphone, color: "text-muted-foreground", body: c.status };
  return {
    id: c.id,
    icon: meta.icon,
    iconColor: meta.color,
    title: c.name,
    body: meta.body,
    timestamp: c.started_at ?? c.created_at,
  };
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
function NotificationBell() {
  const { isAdmin } = useAuth();
  const [open, setOpen]       = useState(false);
  const [items, setItems]     = useState<NotifItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasNew, setHasNew]   = useState(true);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const seen = parseInt(localStorage.getItem("motm_notif_seen") ?? "0", 10);
    // If opened within the last hour, hide dot
    if (Date.now() - seen < 60 * 60 * 1000) setHasNew(false);
  }, []);

  // Close on outside click
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
        const interesting = (data.items ?? [])
          .filter((c) => ["running", "completed", "scheduled", "paused"].includes(c.status))
          .slice(0, 12)
          .map(campaignToNotif);
        setItems(interesting);
      }
      // Mark as seen
      localStorage.setItem("motm_notif_seen", String(Date.now()));
      setHasNew(false);
    } catch {
      // silently fail — bell shouldn't break the UI
    } finally {
      setLoading(false);
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={toggleOpen}
        className="relative h-8 w-8 grid place-items-center rounded-lg transition-all duration-150 text-muted-foreground hover:text-foreground hover:bg-accent"
      >
        <Bell className="h-4 w-4" />
        {hasNew && (
          <span
            className="absolute top-1.5 right-1.5 h-1.5 w-1.5 rounded-full pulse-dot"
            style={{ background: "var(--primary)", boxShadow: "0 0 6px var(--primary)" }}
          />
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-10 z-50 w-80 rounded-xl bg-card border border-border shadow-xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <span className="text-sm font-semibold">Notifications</span>
            <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Body */}
          <div className="max-h-80 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-10">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : items.length === 0 ? (
              <div className="py-10 text-center">
                <Bell className="h-8 w-8 mx-auto text-muted-foreground/30 mb-2" />
                <p className="text-xs text-muted-foreground">No recent activity</p>
              </div>
            ) : (
              <ul>
                {items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <li
                      key={item.id}
                      className="flex items-start gap-3 px-4 py-3 border-b border-border/50 last:border-0 hover:bg-surface-2/40 transition-colors"
                    >
                      <span className={`mt-0.5 shrink-0 ${item.iconColor}`}>
                        <Icon className="h-3.5 w-3.5" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-semibold truncate">{item.title}</p>
                        <p className="text-[11px] text-muted-foreground truncate">{item.body}</p>
                      </div>
                      <span className="text-[10px] text-muted-foreground shrink-0 mt-0.5">
                        {formatAgo(item.timestamp)}
                      </span>
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

// ── Header ────────────────────────────────────────────────────────────────────
export function Header() {
  const path     = useRouterState({ select: (s) => s.location.pathname });
  const segments = path.split("/").filter(Boolean);
  const { isAdmin } = useAuth();

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
        <NotificationBell />

        {/* New Campaign — only for members, not admins */}
        {!isAdmin && (
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
        )}
      </div>
    </header>
  );
}
