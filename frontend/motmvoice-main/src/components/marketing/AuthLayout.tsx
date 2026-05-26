import { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Mic, Zap, Shield, Globe } from "lucide-react";
import { SoundWave } from "./SoundWave";

const FEATURES = [
  { icon: Zap,    text: "1,500+ calls per day on autopilot"         },
  { icon: Globe,  text: "Hinglish, Hindi, English & 20+ languages"  },
  { icon: Shield, text: "Human-like voice with real-time AI"         },
];

// ── Deep navy colour tokens (matches app theme) ──────────────────────────────
const C = {
  bg:          "oklch(0.178 0.030 254)",   // --background deep navy
  bgDeep:      "oklch(0.138 0.024 258)",   // --sidebar deeper navy
  bgCard:      "oklch(0.218 0.032 253)",   // --card
  text:        "oklch(0.938 0.012 255)",   // --foreground near-white
  muted:       "oklch(0.580 0.022 252)",   // --muted-foreground
  border:      "oklch(0.295 0.030 251)",   // --border
  inputBg:     "oklch(0.208 0.030 254)",   // --input
  primary:     "oklch(0.622 0.220 250)",   // --primary electric blue
  primaryFg:   "oklch(0.986 0.006 252)",   // --primary-foreground
  accent:      "oklch(0.280 0.065 252)",   // --accent
  ring:        "oklch(0.622 0.220 250)",   // --ring
  orange:      "oklch(0.70 0.20  45)",     // brand orange accent (logo / glow)
  orangeLight: "oklch(0.80 0.14  50)",     // peach glow
  white:       "oklch(0.988 0.003 255)",
};

export function AuthLayout({
  children, title, subtitle,
}: {
  children: ReactNode; title: string; subtitle: string;
}) {
  return (
    <div
      className="min-h-screen grid lg:grid-cols-2"
      style={{ background: C.bg, color: C.text }}
    >

      {/* ════════════════════════════════════════════════════════════════
          LEFT PANEL — deep navy hero with electric blue glow
      ════════════════════════════════════════════════════════════════ */}
      <div
        className="relative hidden lg:flex flex-col justify-between p-12 overflow-hidden"
        style={{ borderRight: `1px solid ${C.border}`, background: C.bgDeep }}
      >

        {/* Electric blue radial glow top */}
        <div
          className="absolute pointer-events-none"
          style={{
            top: "-20%",
            left: "50%",
            transform: "translateX(-50%)",
            width: "140%",
            height: "70%",
            background: `radial-gradient(ellipse at 50% 0%, oklch(0.622 0.220 250 / 0.28) 0%, oklch(0.590 0.242 278 / 0.12) 45%, transparent 72%)`,
          }}
        />

        {/* Soft blue glow bottom-left */}
        <div
          className="absolute pointer-events-none"
          style={{
            bottom: "-10%",
            left: "-10%",
            width: "60%",
            height: "50%",
            background: `radial-gradient(ellipse, oklch(0.622 0.220 250 / 0.15) 0%, transparent 70%)`,
          }}
        />

        {/* Dot grid texture */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: `radial-gradient(circle, oklch(0.622 0.220 250 / 0.10) 1px, transparent 1px)`,
            backgroundSize: "22px 22px",
          }}
        />

        {/* Logo */}
        <Link to="/" className="relative z-10 flex items-center gap-2.5 w-fit">
          <div
            className="h-9 w-9 rounded-lg grid place-items-center"
            style={{
              background: `linear-gradient(135deg, ${C.orange}, oklch(0.78 0.17 62))`,
              boxShadow: `0 0 20px ${C.orange}40`,
            }}
          >
            <Mic className="h-4 w-4" style={{ color: C.white }} />
          </div>
          <div>
            <div className="font-bold text-[15px] tracking-tight leading-none" style={{ color: C.text }}>
              MOTMVoice
            </div>
            <div className="text-[10px] font-semibold mt-0.5 tracking-wide" style={{ color: C.primary }}>
              AI Voice Platform
            </div>
          </div>
        </Link>

        {/* Hero copy */}
        <div className="relative z-10 space-y-6">
          <div>
            <div
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold tracking-wider uppercase mb-4"
              style={{
                background: `${C.primary}20`,
                border: `1px solid ${C.primary}40`,
                color: C.primary,
              }}
            >
              <span
                className="h-1.5 w-1.5 rounded-full animate-pulse"
                style={{ background: C.primary }}
              />
              Trusted by 200+ Sales Teams
            </div>

            <h2
              className="text-5xl font-heading font-semibold leading-tight tracking-tight"
              style={{ color: C.text }}
            >
              <span
                style={{
                  background: `linear-gradient(135deg, ${C.primary}, oklch(0.590 0.242 278))`,
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  backgroundClip: "text",
                }}
              >
                Voice
              </span>
              <br />
              that converts.
            </h2>

            <p className="mt-4 text-[15px] leading-relaxed max-w-sm" style={{ color: C.muted }}>
              Automate outbound sales calls with AI that sounds human — in any language, at any scale.
            </p>
          </div>

          {/* Feature pills */}
          <ul className="space-y-3">
            {FEATURES.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-sm" style={{ color: C.muted }}>
                <div
                  className="h-7 w-7 rounded-lg grid place-items-center shrink-0"
                  style={{ background: `${C.primary}18`, color: C.primary }}
                >
                  <Icon className="h-3.5 w-3.5" />
                </div>
                {text}
              </li>
            ))}
          </ul>

          {/* Live calls widget */}
          <div
            className="rounded-xl p-5"
            style={{
              background: `${C.bgCard}cc`,
              backdropFilter: "blur(16px)",
              WebkitBackdropFilter: "blur(16px)",
              border: `1px solid ${C.border}`,
            }}
          >
            <SoundWave bars={32} />
            <div
              className="mt-3 flex items-center justify-between text-xs"
              style={{ color: C.muted }}
            >
              <span className="flex items-center gap-1.5">
                <span
                  className="h-1.5 w-1.5 rounded-full pulse-dot"
                  style={{ background: "oklch(0.70 0.16 160)" }}
                />
                Live calls in progress
              </span>
              <span className="font-mono font-semibold" style={{ color: C.text }}>
                1,247 today
              </span>
            </div>
          </div>
        </div>

        <div className="relative z-10 text-xs" style={{ color: `${C.muted}80` }}>
          © 2026 MOTMVoice · All rights reserved
        </div>
      </div>

      {/* ════════════════════════════════════════════════════════════════
          RIGHT PANEL — form
      ════════════════════════════════════════════════════════════════ */}
      <div
        className="flex items-center justify-center p-6 lg:p-12 relative"
        style={{ background: C.bg }}
      >
        {/* Subtle blue glow top-right */}
        <div
          className="absolute top-0 right-0 pointer-events-none"
          style={{
            width: "300px",
            height: "300px",
            background: `radial-gradient(circle, oklch(0.622 0.220 250 / 0.12) 0%, transparent 70%)`,
          }}
        />

        <div className="relative w-full max-w-sm fade-up">

          {/* Mobile logo */}
          <div className="lg:hidden mb-8 flex items-center gap-2.5">
            <div
              className="h-9 w-9 rounded-lg grid place-items-center"
              style={{
                background: `linear-gradient(135deg, ${C.orange}, oklch(0.78 0.17 62))`,
                boxShadow: `0 0 20px ${C.orange}40`,
              }}
            >
              <Mic className="h-4 w-4" style={{ color: C.white }} />
            </div>
            <div>
              <div className="font-bold text-[15px] tracking-tight leading-none" style={{ color: C.text }}>
                MOTMVoice
              </div>
              <div className="text-[10px] font-semibold mt-0.5" style={{ color: C.primary }}>
                AI Voice Platform
              </div>
            </div>
          </div>

          {/* Heading */}
          <h1
            className="text-[28px] font-heading font-semibold tracking-tight"
            style={{ color: C.text }}
          >
            {title}
          </h1>
          <p className="mt-1.5 text-sm" style={{ color: C.muted }}>
            {subtitle}
          </p>

          {/* Form — CSS variable overrides so all child components use navy */}
          <div
            className="mt-8"
            style={{
              "--foreground":          C.text,
              "--muted-foreground":    C.muted,
              "--border":              C.border,
              "--background":          C.bg,
              "--card":                C.bgCard,
              "--input":               C.inputBg,
              "--primary":             C.primary,
              "--primary-foreground":  C.primaryFg,
              "--ring":                C.ring,
              "--accent":              C.accent,
              "--accent-foreground":   C.text,
            } as React.CSSProperties}
          >
            {children}
          </div>
        </div>
      </div>

    </div>
  );
}
