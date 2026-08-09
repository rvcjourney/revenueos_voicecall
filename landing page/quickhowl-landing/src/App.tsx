import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@/lib/theme";
import LandingPage from "@/routes/LandingPage";

const queryClient = new QueryClient();

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <LandingPage />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
