import { useEffect, useState } from "react";

const WAVE_DELAYS = [0, 0.12, 0.22, 0.08, 0.32, 0.18, 0.28, 0.04, 0.36, 0.14, 0.24, 0.06, 0.30, 0.16, 0.40, 0.10];
const WAVE_HEIGHTS = [16, 32, 44, 28, 48, 36, 52, 24, 44, 40, 20, 36, 48, 28, 40, 18];

export function SplashScreen() {
  const [visible, setVisible] = useState(false);
  const [phase, setPhase] = useState<"in" | "hold" | "out">("in");

  useEffect(() => {
    if (sessionStorage.getItem("motm_splash_done")) return;
    sessionStorage.setItem("motm_splash_done", "1");
    setVisible(true);

    const t1 = setTimeout(() => setPhase("hold"), 600);
    const t2 = setTimeout(() => setPhase("out"), 2400);
    const t3 = setTimeout(() => setVisible(false), 3200);
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
  }, []);

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
          <div className="splash-logo">
            <svg width="42" height="42" viewBox="0 0 42 42" fill="none">
              <path
                d="M6 36V10L21 24L36 10V36"
                stroke="white"
                strokeWidth="3.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <div className="splash-logo-ring" />
          </div>
        </div>

        {/* Brand name */}
        <div className="splash-brand">
          <span className="splash-brand-motm">MOTM</span>
          <span className="splash-brand-voice">Voice</span>
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

        {/* Version label */}
        <div className="splash-version">Powered by LiveKit · ElevenLabs · Groq</div>
      </div>
    </div>
  );
}
