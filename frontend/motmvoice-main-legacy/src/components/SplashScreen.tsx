import { useEffect, useState } from "react";
import { LogoMark } from "@/components/Logo";

const WAVE_DELAYS  = [0, 0.12, 0.22, 0.08, 0.32, 0.18, 0.28, 0.04, 0.36, 0.14, 0.24, 0.06, 0.30, 0.16, 0.40, 0.10];
const WAVE_HEIGHTS = [16, 32, 44, 28, 48, 36, 52, 24, 44, 40, 20, 36, 48, 28, 40, 18];

// "MOTM" letters stagger from 0.45s, "Voice" from 0.80s
const MOTM_DELAYS  = [0.45, 0.52, 0.59, 0.66];
const VOICE_DELAYS = [0.82, 0.89, 0.96, 1.03, 1.10];

export function SplashScreen() {
  // Start hidden — the inline <script> in <head> already hid #app-root via CSS.
  // useEffect will show the splash after hydration.
  const [visible, setVisible] = useState(false);
  const [phase, setPhase]     = useState<"in" | "hold" | "out">("in");

  useEffect(() => {
    // If the inline script did NOT add splash-active (already visited), skip.
    if (!document.documentElement.classList.contains("splash-active")) return;

    try { sessionStorage.setItem("motm_splash_done", "1"); } catch { /* noop */ }

    setVisible(true);

    const t1 = setTimeout(() => setPhase("hold"), 700);
    const t2 = setTimeout(() => setPhase("out"),  2600);
    const t3 = setTimeout(() => {
      setVisible(false);
      // Removing the class triggers the CSS transition that reveals #app-root
      document.documentElement.classList.remove("splash-active");
    }, 3500);

    return () => {
      clearTimeout(t1); clearTimeout(t2); clearTimeout(t3);
      document.documentElement.classList.remove("splash-active");
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!visible) return null;

  return (
    <div className="splash-root" data-phase={phase}>

      {/* Ambient orbs */}
      <div className="splash-orb splash-orb-1" />
      <div className="splash-orb splash-orb-2" />
      <div className="splash-orb splash-orb-3" />

      {/* Grid overlay */}
      <div className="splash-grid" />

      {/* Content */}
      <div className="splash-content">

        {/* Logo badge */}
        <div className="splash-logo-wrap">
          <div className="splash-logo-inner">
            <LogoMark size={88} />
          </div>
          <div className="splash-logo-ring" />
        </div>

        {/* Brand name — letter by letter */}
        <div className="splash-brand">
          <span className="splash-brand-motm-wrap">
            {["M","O","T","M"].map((l, i) => (
              <span
                key={i}
                className="splash-letter splash-letter-bold"
                style={{ animationDelay: `${MOTM_DELAYS[i]}s` }}
              >{l}</span>
            ))}
          </span>
          <span className="splash-brand-voice-wrap">
            {["V","o","i","c","e"].map((l, i) => (
              <span
                key={i}
                className="splash-letter splash-letter-light"
                style={{ animationDelay: `${VOICE_DELAYS[i]}s` }}
              >{l}</span>
            ))}
          </span>
        </div>

        {/* Tagline */}
        <div className="splash-tagline">AI Voice Sales Automation</div>

        {/* Audio wave */}
        <div className="splash-wave">
          {WAVE_DELAYS.map((delay, i) => (
            <div
              key={i}
              className="splash-wave-bar"
              style={{
                animationDelay: `${delay}s`,
                maxHeight: `${WAVE_HEIGHTS[i]}px`,
              }}
            />
          ))}
        </div>

        {/* Credits */}
        <div className="splash-version">Powered by LiveKit · ElevenLabs · Groq</div>
      </div>
    </div>
  );
}
