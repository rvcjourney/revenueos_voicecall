import { Link, useRouterState } from "@tanstack/react-router";
import { Mic, LayoutDashboard, Megaphone, Phone, Bot, BarChart3, Plug, Settings, LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useNavigate } from "@tanstack/react-router";

const items = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/campaigns", label: "Campaigns", icon: Megaphone },
  { to: "/calls", label: "Call History", icon: Phone },
  { to: "/agents", label: "AI Agents", icon: Bot },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/integrations", label: "Integrations", icon: Plug },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

export function Sidebar() {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <aside className="hidden md:flex flex-col w-60 shrink-0 bg-sidebar border-r border-sidebar-border h-screen sticky top-0">
      <Link to="/dashboard" className="flex items-center gap-2 px-5 h-16 border-b border-sidebar-border">
        <div className="h-8 w-8 rounded-lg bg-gradient-primary grid place-items-center shadow-glow">
          <Mic className="h-4 w-4 text-white" />
        </div>
        <span className="font-bold tracking-tight">MOTMVoice</span>
      </Link>
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        {items.map((it) => {
          const active = path === it.to || (it.to !== "/dashboard" && path.startsWith(it.to));
          return (
            <Link
              key={it.to}
              to={it.to}
              className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                active
                  ? "bg-primary/15 text-foreground border border-primary/20"
                  : "text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
              }`}
            >
              <it.icon className="h-4 w-4" />
              {it.label}
            </Link>
          );
        })}
      </nav>
      <div className="p-3 border-t border-sidebar-border">
        <div className="flex items-center gap-3 p-2 rounded-md bg-sidebar-accent/40">
          <div className="h-9 w-9 rounded-full bg-gradient-primary grid place-items-center text-white text-sm font-semibold shrink-0">
            {user?.full_name?.[0] ?? "A"}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium truncate">{user?.full_name ?? "Guest"}</div>
            <div className="text-xs text-muted-foreground truncate">
              <span className="inline-block px-1.5 py-0.5 rounded bg-primary/15 text-primary text-[10px] font-semibold mr-1">PRO</span>
              {user?.role ?? "Manager"}
            </div>
          </div>
          <button
            onClick={() => { logout(); navigate({ to: "/login" }); }}
            className="text-muted-foreground hover:text-foreground"
            title="Logout"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
