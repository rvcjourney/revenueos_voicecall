import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  useRouterState,
  HeadContent,
  Scripts,
} from "@tanstack/react-router";

const GA_ID = "G-DKK08XT10J";

import appCss from "../styles.css?url";
import { AuthProvider } from "@/lib/auth";
import { Toaster } from "@/components/ui/sonner";
import { ThemeProvider, useTheme } from "@/lib/theme";
import { SplashScreen } from "@/components/SplashScreen";

// Single fixed theme — no flash script needed.

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-foreground">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-foreground">Page not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  console.error(error);
  const router = useRouter();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          This page didn't load
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Something went wrong on our end. You can try refreshing or head back home.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Try again
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "MOTMVoice — AI Voice Call Automation" },
      { name: "description", content: "Automate 1500+ outbound sales calls daily with human-like AI voice agents in Hinglish, English & 20+ languages." },
      { name: "author", content: "MOTMVoice" },
      { property: "og:title", content: "MOTMVoice — AI Voice Sales Call Automation" },
      { property: "og:description", content: "Automate 1500+ outbound sales calls daily with human-like AI voice agents in Hinglish, English & 20+ languages." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
      { name: "twitter:site", content: "@MOTMVoice" },
      { name: "twitter:title", content: "MOTMVoice — AI Voice Sales Call Automation" },
      { name: "twitter:description", content: "Automate 1500+ outbound sales calls daily with human-like AI voice agents in Hinglish, English & 20+ languages." },
      { property: "og:image", content: "https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/5bfc159f-9938-44a6-87ef-480fc4f3f0ff/id-preview-581813a5--7cde9053-4ad5-466b-bf7b-f74af439a567.lovable.app-1778579282497.png" },
      { name: "twitter:image", content: "https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/5bfc159f-9938-44a6-87ef-480fc4f3f0ff/id-preview-581813a5--7cde9053-4ad5-466b-bf7b-f74af439a567.lovable.app-1778579282497.png" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
      { rel: "stylesheet", href: "https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700;800&family=Geist+Mono:wght@400;500;600&family=Lora:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&display=swap" },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <HeadContent />
        {/* Splash guard — runs synchronously before any paint.
            Adds 'splash-active' to <html> if this is the first visit this session.
            CSS hides #app-root while this class is present, so dashboard never
            flashes before the splash animation plays. */}
        <script dangerouslySetInnerHTML={{ __html:
          `(function(){try{if(!sessionStorage.getItem('motm_splash_done')){` +
          `document.documentElement.classList.add('splash-active');` +
          `}}catch(e){}})();`
        }} />
        <script async src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`} />
        <script
          dangerouslySetInnerHTML={{
            __html: `window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}gtag('js',new Date());gtag('config','${GA_ID}',{send_page_view:false});`,
          }}
        />
      </head>
      <body className="bg-background text-foreground antialiased">
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function Analytics() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  useEffect(() => {
    (window as any).gtag?.("event", "page_view", {
      page_location: window.location.href,
      page_path: pathname,
    });
  }, [pathname]);
  return null;
}

/** Toaster that follows the active theme automatically */
function ThemedToaster() {
  const { theme } = useTheme();
  return <Toaster theme={theme} position="top-right" />;
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <SplashScreen />
          <div id="app-root">
            <Analytics />
            <Outlet />
            <ThemedToaster />
          </div>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
