import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Megaphone,
  Phone,
  BarChart3,
  Headset,
  Mic,
  Users,
  PhoneCall,
  PhoneIncoming,
  ShieldBan,
  ClipboardList,
  CreditCard,
  Settings,
  ChevronsLeft,
  ChevronsRight,
  LogOut,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { RoleBadge } from "@/components/shared/StatusBadge";
import { Logo, LogoMark } from "@/components/shared/Logo";
import { cn, initials } from "@/lib/utils";
import { toast } from "sonner";

const mainNav = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/campaigns", label: "Campaigns", icon: Megaphone },
  { to: "/calls", label: "Call History", icon: Phone },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/agents", label: "AI Agents", icon: Headset },
];

const adminNav = [
  { to: "/admin/team", label: "Team", icon: Users },
  { to: "/admin/phone-numbers", label: "Phone Numbers", icon: PhoneCall },
  { to: "/admin/inbound-agents", label: "Inbound Agents", icon: PhoneIncoming },
  { to: "/voice-cloning", label: "Voice Cloning", icon: Mic },
  { to: "/admin/dnc", label: "DNC List", icon: ShieldBan },
  { to: "/admin/audit", label: "Audit Log", icon: ClipboardList },
];

const SIDEBAR_COLLAPSED_KEY = "motmvoice-sidebar-collapsed";

function readStoredCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
}

export function Sidebar() {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(readStoredCollapsed);

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed));
  }, [collapsed]);

  async function handleLogout() {
    await logout();
    toast.success("Signed out");
    navigate("/login");
  }

  return (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col rounded-2xl border border-sidebar-border bg-sidebar shadow-[var(--shadow-elevated)] transition-[width] duration-200",
        collapsed ? "w-[76px]" : "w-64"
      )}
    >
      <div className="flex items-center justify-between px-4 py-5">
        {collapsed ? <LogoMark /> : <Logo className="text-sidebar-foreground" />}
      </div>

      <nav className="flex-1 space-y-6 overflow-y-auto px-3 pb-4">
        <div className="space-y-1">
          {!collapsed && (
            <p className="px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wider text-sidebar-foreground/35">
              Workspace
            </p>
          )}
          {mainNav.map((item) => (
            <NavItem key={item.to} {...item} collapsed={collapsed} />
          ))}
        </div>

        {isAdmin && (
          <div className="space-y-1">
            {!collapsed && (
              <p className="px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wider text-sidebar-foreground/35">
                Admin
              </p>
            )}
            {adminNav.map((item) => (
              <NavItem key={item.to} {...item} collapsed={collapsed} />
            ))}
          </div>
        )}

        <div className="space-y-1">
          <NavItem to="/billing" label="Billing" icon={CreditCard} collapsed={collapsed} />
          <NavItem to="/settings" label="Settings" icon={Settings} collapsed={collapsed} />
        </div>
      </nav>

      <div className="border-t border-sidebar-border p-3">
        <button
          onClick={() => setCollapsed((v) => !v)}
          className="mb-2 flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs text-sidebar-foreground/50 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
        >
          {collapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
          {!collapsed && "Collapse"}
        </button>
        <div className={cn("flex items-center gap-2 rounded-xl p-2", !collapsed && "bg-sidebar-accent")}>
          <Avatar className="h-8 w-8 border border-sidebar-border">
            <AvatarFallback className="bg-[image:var(--gradient-primary)] text-primary-foreground">
              {initials(user?.full_name ?? "?")}
            </AvatarFallback>
          </Avatar>
          {!collapsed && (
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-sidebar-foreground">{user?.full_name}</p>
              <RoleBadge role={user?.role ?? "member"} className="mt-0.5" />
            </div>
          )}
          <button
            onClick={handleLogout}
            title="Log out"
            className="rounded-md p-1.5 text-sidebar-foreground/45 transition-colors hover:bg-sidebar-border hover:text-sidebar-foreground"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}

function NavItem({
  to,
  label,
  icon: Icon,
  collapsed,
}: {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  collapsed: boolean;
}) {
  return (
    <NavLink
      to={to}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        cn(
          "relative flex items-center gap-3 rounded-lg py-2 text-sm font-medium transition-colors",
          collapsed ? "justify-center px-1.5" : "px-2.5",
          isActive
            ? "bg-sidebar-accent-strong text-sidebar-foreground"
            : "text-sidebar-foreground/55 hover:bg-sidebar-accent hover:text-sidebar-foreground"
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <span className="absolute -left-3 top-1/2 h-5 w-1 -translate-y-1/2 rounded-full bg-primary" />
          )}
          <span
            className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors",
              isActive ? "bg-primary text-primary-foreground shadow-[var(--shadow-glow)]" : "bg-transparent"
            )}
          >
            <Icon className="h-4 w-4" />
          </span>
          {!collapsed && <span className={cn("truncate", isActive && "font-semibold")}>{label}</span>}
        </>
      )}
    </NavLink>
  );
}
