import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { Logo } from "@/components/shared/Logo";
import { SoundWave } from "@/components/shared/SoundWave";

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
    <div className="relative grid min-h-screen lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-card to-background p-10 lg:flex">
        <div className="dot-grid absolute inset-0 opacity-40" />
        <div className="relative">
          <Link to="/">
            <Logo />
          </Link>
        </div>
        <div className="relative space-y-6">
          <SoundWave className="h-16" />
          <blockquote className="max-w-md font-heading text-2xl leading-snug text-foreground">
            "Our AI agents made 12,000 calls last month — in Hinglish, at scale, without hiring a single extra rep."
          </blockquote>
          <p className="text-sm text-muted-foreground">Sales Ops Lead, mid-market SaaS company</p>
        </div>
        <p className="relative text-xs text-muted-foreground">
          Trusted by outbound sales teams across India
        </p>
      </div>

      <div className="flex items-center justify-center px-4 py-12 sm:px-6">
        <div className="w-full max-w-sm space-y-8">
          <div className="space-y-2 lg:hidden">
            <Link to="/">
              <Logo />
            </Link>
          </div>
          <div className="space-y-1.5">
            <h1 className="font-heading text-2xl font-semibold">{title}</h1>
            <p className="text-sm text-muted-foreground">{subtitle}</p>
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
