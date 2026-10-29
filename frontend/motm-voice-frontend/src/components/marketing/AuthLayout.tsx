import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { Logo } from "@/components/shared/Logo";
import { ThemeToggle } from "@/components/shared/ThemeToggle";

// Background video lives at public/auth-bg.mp4. If the file is missing the
// dark background shows instead, so the page never breaks.
export function AuthLayout({
  title,
  subtitle,
  wide = false,
  children,
}: {
  title: string;
  subtitle: string;
  // Signup's two-column form needs more room; login stays a compact square
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-neutral-950 px-4 pb-4 pt-20 sm:px-6 sm:pt-4">
      <video
        className="absolute inset-0 h-full w-full object-cover motion-reduce:hidden"
        src="/auth-bg.mp4"
        autoPlay
        muted
        loop
        playsInline
        aria-hidden="true"
      />
      {/* Always dark: a light overlay washes the video out to grey in light mode */}
      <div className="absolute inset-0 bg-black/50" />

      {/* "dark" keeps the logo text light, since it always sits on the dark video */}
      <Link to="/" className="dark absolute left-4 top-4 z-10 text-foreground sm:left-6">
        <Logo />
      </Link>
      <div className="absolute right-4 top-4 z-10 sm:right-6">
        <ThemeToggle />
      </div>

      <div className={`relative w-full ${wide ? "max-w-xl" : "max-w-md"} space-y-4 rounded-2xl border border-border/60 bg-card/80 p-6 shadow-2xl backdrop-blur-md`}>
        <div className="space-y-1">
          <h1 className="font-heading text-xl font-semibold">{title}</h1>
          <p className="text-sm text-muted-foreground">{subtitle}</p>
        </div>
        {children}
      </div>
    </div>
  );
}
