import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { PageLoader } from "@/components/shared/PageLoader";
import { SubscriptionBanner } from "@/components/billing/SubscriptionBanner";

export function AuthedLayout() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <PageLoader />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return (
    <div className="dot-grid min-h-screen bg-background p-3 lg:p-4">
      <div className="mx-auto flex h-[calc(100vh-1.5rem)] max-w-[1680px] gap-4 lg:h-[calc(100vh-2rem)]">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <TopBar />
          <main className="min-w-0 flex-1 overflow-y-auto rounded-2xl border border-border bg-card/70 px-4 py-6 shadow-[var(--shadow-card)] backdrop-blur-sm sm:px-6 lg:px-8 lg:py-8">
            <div className="mx-auto max-w-7xl">
              <SubscriptionBanner />
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
