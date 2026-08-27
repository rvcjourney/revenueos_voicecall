import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@/lib/theme";
import LandingPage from "@/routes/LandingPage";
import PrivacyPolicy from "@/routes/PrivacyPolicy";
import TermsOfService from "@/routes/TermsOfService";

const queryClient = new QueryClient();

// No router library here on purpose -- this is a single marketing site with
// a couple of extra static legal pages, not worth pulling in react-router-dom
// for. `serve -s dist` (Dockerfile) already falls back to index.html for any
// path, so a direct visit to /privacy-policy or /terms-of-service works in
// production too.
function CurrentRoute() {
  if (window.location.pathname === "/privacy-policy") return <PrivacyPolicy />;
  if (window.location.pathname === "/terms-of-service") return <TermsOfService />;
  return <LandingPage />;
}

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <CurrentRoute />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
