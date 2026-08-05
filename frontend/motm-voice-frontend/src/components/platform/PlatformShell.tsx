import { BarChart3, Building2, LayoutDashboard, Layers, LogOut, Mic } from "lucide-react";
import { NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { usePlatformAuth } from "@/lib/platformAuth";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/ops/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/ops/organizations", label: "Organizations", icon: Building2 },
  { to: "/ops/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/ops/plans", label: "Plans", icon: Layers },
  { to: "/ops/voice-clone-requests", label: "Voice Requests", icon: Mic },
];

/** Route guard + chrome for everything under /ops, gated on the platform (not tenant) session. */
export function PlatformAuthedLayout() {
  const { isAuthenticated } = usePlatformAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/ops/login" replace state={{ from: location.pathname }} />;
  }

  return (
    <div className="min-h-screen bg-background">
      <PlatformTopBar />
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <Outlet />
      </main>
    </div>
  );
}

function PlatformTopBar() {
  const { admin, logout } = usePlatformAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/ops/login", { replace: true });
  }

  return (
    <header className="border-b border-border bg-card">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
        <div className="flex items-center gap-6">
          <span className="text-sm font-semibold tracking-tight text-foreground">
            QuickHowl <span className="font-normal text-muted-foreground">Platform Console</span>
          </span>
          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-muted text-foreground"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                  )
                }
              >
                <item.icon className="h-3.5 w-3.5" />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">{admin?.email}</span>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <LogOut className="h-3.5 w-3.5" /> Log out
          </button>
        </div>
      </div>
    </header>
  );
}
