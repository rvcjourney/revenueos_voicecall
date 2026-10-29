import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { Logo } from "@/components/shared/Logo";
import { ThemeToggle } from "@/components/shared/ThemeToggle";

// Background video lives at public/auth-bg.mp4. If the file is missing the
// gradient underneath shows instead, so the page never breaks.
export function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-to-br from-card to-background px-4 pb-4 pt-20 sm:px-6 sm:pt-4">
      <video
        className="absolute inset-0 h-full w-full object-cover motion-reduce:hidden"
        src="/auth-bg.mp4"
        autoPlay
        muted
        loop
        playsInline
        aria-hidden="true"
      />
      {/* Dims the video so the card stays readable in light and dark mode */}
      <div className="absolute inset-0 bg-background/60" />

      <Link to="/" className="absolute left-4 top-4 z-10 sm:left-6">
        <Logo />
      </Link>
      <div className="absolute right-4 top-4 z-10 sm:right-6">
        <ThemeToggle />
      </div>

      <div className="relative w-full max-w-xl space-y-4 rounded-2xl border border-border/60 bg-card/80 p-6 shadow-2xl backdrop-blur-md">
        <div className="space-y-1">
          <h1 className="font-heading text-xl font-semibold">{title}</h1>
          <p className="text-sm text-muted-foreground">{subtitle}</p>
        </div>
        {children}
      </div>
    </div>
  );
}
