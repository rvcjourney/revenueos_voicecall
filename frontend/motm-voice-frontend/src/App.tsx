import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/lib/auth";
import { PlatformAuthProvider } from "@/lib/platformAuth";
import { ThemeProvider } from "@/lib/theme";
import { AuthedLayout } from "@/components/layout/AuthedLayout";
import { PlatformAuthedLayout } from "@/components/platform/PlatformShell";
import { PageLoader } from "@/components/shared/PageLoader";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";

const Landing = lazy(() => import("@/routes/Landing"));
const Login = lazy(() => import("@/routes/Login"));
const Signup = lazy(() => import("@/routes/Signup"));
const ForgotPassword = lazy(() => import("@/routes/ForgotPassword"));
const NotFound = lazy(() => import("@/routes/NotFound"));

const Dashboard = lazy(() => import("@/routes/Dashboard"));
const CampaignsList = lazy(() => import("@/routes/CampaignsList"));
const CampaignNew = lazy(() => import("@/routes/CampaignNew"));
const CampaignDetail = lazy(() => import("@/routes/CampaignDetail"));
const CallsList = lazy(() => import("@/routes/CallsList"));
const CallDetail = lazy(() => import("@/routes/CallDetail"));
const Agents = lazy(() => import("@/routes/Agents"));
const PromptLibrary = lazy(() => import("@/routes/PromptLibrary"));
const VoiceCloning = lazy(() => import("@/routes/VoiceCloning"));
const Analytics = lazy(() => import("@/routes/Analytics"));
const Billing = lazy(() => import("@/routes/Billing"));
const Settings = lazy(() => import("@/routes/Settings"));
const AdminTeam = lazy(() => import("@/routes/admin/AdminTeam"));
const AdminPhoneNumbers = lazy(() => import("@/routes/admin/AdminPhoneNumbers"));
const InboundAgents = lazy(() => import("@/routes/admin/InboundAgents"));
const AdminDnc = lazy(() => import("@/routes/admin/AdminDnc"));
const AdminAudit = lazy(() => import("@/routes/admin/AdminAudit"));

// SuperAdmin / Platform Console — separate route namespace, auth context, and
// token storage from the tenant app above. Never linked from tenant nav.
const PlatformLogin = lazy(() => import("@/routes/platform/PlatformLogin"));
const PlatformDashboard = lazy(() => import("@/routes/platform/PlatformDashboard"));
const PlatformOrganizations = lazy(() => import("@/routes/platform/PlatformOrganizations"));
const PlatformOrgDetail = lazy(() => import("@/routes/platform/PlatformOrgDetail"));
const PlatformPlans = lazy(() => import("@/routes/platform/PlatformPlans"));
const PlatformVoiceCloneRequests = lazy(() => import("@/routes/platform/PlatformVoiceCloneRequests"));
const PlatformAnalytics = lazy(() => import("@/routes/platform/PlatformAnalytics"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      // Data younger than this is served straight from cache with no background
      // refetch — stops re-visiting a recently-seen page from firing a redundant
      // request that competes with the new page's own (first-load) requests.
      staleTime: 15_000,
    },
  },
});

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <AuthProvider>
            <TooltipProvider delayDuration={200}>
              <BrowserRouter>
                <Suspense fallback={<PageLoader />}>
                  <Routes>
                    <Route path="/" element={<Landing />} />
                    <Route path="/login" element={<Login />} />
                    <Route path="/signup" element={<Signup />} />
                    <Route path="/forgot-password" element={<ForgotPassword />} />

                    <Route element={<AuthedLayout />}>
                      <Route path="/dashboard" element={<Dashboard />} />
                      <Route path="/campaigns" element={<CampaignsList />} />
                      <Route path="/campaigns/new" element={<CampaignNew />} />
                      <Route path="/campaigns/:id" element={<CampaignDetail />} />
                      <Route path="/calls" element={<CallsList />} />
                      <Route path="/calls/:id" element={<CallDetail />} />
                      <Route path="/agents" element={<Agents />} />
                      <Route path="/prompt-library" element={<PromptLibrary />} />
                      <Route path="/voice-cloning" element={<VoiceCloning />} />
                      <Route path="/analytics" element={<Analytics />} />
                      <Route path="/billing" element={<Billing />} />
                      <Route path="/settings" element={<Settings />} />
                      <Route path="/admin/team" element={<AdminTeam />} />
                      <Route path="/admin/phone-numbers" element={<AdminPhoneNumbers />} />
                      <Route path="/admin/inbound-agents" element={<InboundAgents />} />
                      <Route path="/admin/dnc" element={<AdminDnc />} />
                      <Route path="/admin/audit" element={<AdminAudit />} />
                    </Route>

                    <Route path="/app" element={<Navigate to="/dashboard" replace />} />

                    <Route
                      path="/ops/*"
                      element={
                        <PlatformAuthProvider>
                          <Outlet />
                        </PlatformAuthProvider>
                      }
                    >
                      <Route path="login" element={<PlatformLogin />} />
                      <Route element={<PlatformAuthedLayout />}>
                        <Route index element={<Navigate to="/ops/dashboard" replace />} />
                        <Route path="dashboard" element={<PlatformDashboard />} />
                        <Route path="organizations" element={<PlatformOrganizations />} />
                        <Route path="organizations/:id" element={<PlatformOrgDetail />} />
                        <Route path="plans" element={<PlatformPlans />} />
                        <Route path="voice-clone-requests" element={<PlatformVoiceCloneRequests />} />
                        <Route path="analytics" element={<PlatformAnalytics />} />
                      </Route>
                    </Route>

                    <Route path="*" element={<NotFound />} />
                  </Routes>
                </Suspense>
              </BrowserRouter>
              <Toaster position="top-right" />
            </TooltipProvider>
          </AuthProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
