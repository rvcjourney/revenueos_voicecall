import { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Mic, Zap, Shield, Globe } from "lucide-react";
import { SoundWave } from "./SoundWave";

const FEATURES = [
  { icon: Zap,    text: "1,500+ calls per day on autopilot"         },
  { icon: Globe,  text: "Hinglish, Hindi, English & 20+ languages"  },
  { icon: Shield, text: "Human-like voice with real-time AI"         },
];

export function AuthLayout({
  children, title, subtitle,
}: {
  children: ReactNode; title: string; subtitle: string;
}) {
  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-background">

      {/* ── Left panel ─────────────────────────────────────────────────── */}
      <div className="relative hidden lg:flex flex-col justify-between p-12 overflow-hidden border-r border-border/50">

        {/* Dot-grid texture */}
        <div className="absolute inset-0 dot-grid opacity-[0.12] pointer-events-none" />

        {/* Orange radial glows */}
        <div className="absolute -top-32 -right-32 w-96 h-96 rounded-full bg-primary/10 blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 w-64 h-64 rounded-full bg-primary/6 blur-3xl pointer-events-none" />

        {/* Logo */}
        <Link to="/" className="relative z-10 flex items-center gap-2.5 w-fit">
          <div className="h-9 w-9 rounded-lg bg-gradient-primary grid place-items-center shadow-glow float-glow">
            <Mic className="h-4 w-4 text-white" />
          </div>
          <div>
            <div className="font-bold text-[15px] tracking-tight leading-none">MOTMVoice</div>
            <div className="text-[10px] text-primary font-medium mt-0.5 tracking-wide">AI Voice Platform</div>
          </div>
        </Link>

        {/* Hero copy */}
        <div className="relative z-10 space-y-6">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-[11px] font-semibold tracking-wider uppercase mb-4">
              <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
              Trusted by 200+ Sales Teams
            </div>
            <h2 className="text-5xl font-heading font-semibold leading-tight">
              <span className="text-gradient-warm">Voice</span>
              <br />
              <span className="text-foreground">that converts.</span>
            </h2>
            <p className="mt-4 text-[15px] text-muted-foreground leading-relaxed max-w-sm">
              Automate outbound sales calls with AI that sounds human — in any language, at any scale.
            </p>
          </div>

          {/* Feature list */}
          <ul className="space-y-3">
            {FEATURES.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-sm text-muted-foreground">
                <div className="h-7 w-7 rounded-lg bg-primary/10 grid place-items-center text-primary shrink-0">
                  <Icon className="h-3.5 w-3.5" />
                </div>
                {text}
              </li>
            ))}
          </ul>

          {/* Live calls widget */}
          <div className="glass rounded-xl p-5 border border-primary/10">
            <SoundWave bars={32} />
            <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-success pulse-dot" />
                Live calls in progress
              </span>
              <span className="font-mono text-foreground font-semibold">1,247 today</span>
            </div>
          </div>
        </div>

        <div className="relative z-10 text-xs text-muted-foreground/50">
          © 2026 MOTMVoice · All rights reserved
        </div>
      </div>

      {/* ── Right panel (form) ──────────────────────────────────────────── */}
      <div className="flex items-center justify-center p-6 lg:p-12 relative">
        {/* Subtle background glow */}
        <div className="absolute top-0 right-0 w-72 h-72 rounded-full bg-primary/4 blur-3xl pointer-events-none" />

        <div className="relative w-full max-w-sm fade-up">
          {/* Mobile logo */}
          <div className="lg:hidden mb-8 flex items-center gap-2.5">
            <div className="h-9 w-9 rounded-lg bg-gradient-primary grid place-items-center shadow-glow">
              <Mic className="h-4 w-4 text-white" />
            </div>
            <div>
              <div className="font-bold text-[15px] tracking-tight leading-none">MOTMVoice</div>
              <div className="text-[10px] text-primary font-medium mt-0.5">AI Voice Platform</div>
            </div>
          </div>

          {/* Heading */}
          <h1 className="text-[28px] font-bold tracking-tight">{title}</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">{subtitle}</p>

          <div className="mt-8">{children}</div>
        </div>
      </div>

    </div>
  );
}
