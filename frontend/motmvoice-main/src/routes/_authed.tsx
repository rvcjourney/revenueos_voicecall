import { createFileRoute, Outlet, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/_authed")({
  component: AuthedLayout,
});

function AuthedLayout() {
  const { user } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (typeof window === "undefined") return;
    // Check both React state and localStorage so we catch token expiry
    const hasStoredUser = !!localStorage.getItem("motm_user");
    if (!user && !hasStoredUser) {
      navigate({ to: "/login" });
    }
  }, [user, navigate]);

  return (
    <div className="flex min-h-screen w-full">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />
        <main className="flex-1 p-6 fade-up">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
