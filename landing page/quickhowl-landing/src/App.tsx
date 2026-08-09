import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LandingPage from "@/routes/LandingPage";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <LandingPage />
    </QueryClientProvider>
  );
}
