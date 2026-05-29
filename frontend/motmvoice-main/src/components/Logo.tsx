import { useId } from "react";

/**
 * LogoMark — the icon badge only (rounded square + M + signal bars).
 * Uses useId() so multiple instances on the same page don't share gradient IDs.
 */
export function LogoMark({ size = 40, className = "" }: { size?: number; className?: string }) {
  const uid  = useId().replace(/:/g, "");
  const bgId = `${uid}bg`;
  const hlId = `${uid}hl`;
  const glId = `${uid}gl`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="MOTMVoice logo"
    >
      <defs>
        {/* Deep blue → violet diagonal gradient */}
        <linearGradient id={bgId} x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#1e3a8a" />   {/* blue-800  */}
          <stop offset="50%"  stopColor="#2d3f9e" />   {/* mid       */}
          <stop offset="100%" stopColor="#5b21b6" />   {/* violet-800*/}
        </linearGradient>

        {/* Top-left specular highlight */}
        <radialGradient id={hlId} cx="28%" cy="22%" r="60%">
          <stop offset="0%"   stopColor="white" stopOpacity="0.22" />
          <stop offset="100%" stopColor="white" stopOpacity="0"    />
        </radialGradient>

        {/* Outer glow filter */}
        <filter id={glId} x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      {/* ── Badge background ─────────────────────────────────── */}
      <rect width="40" height="40" rx="10" fill={`url(#${bgId})`} />
      <rect width="40" height="40" rx="10" fill={`url(#${hlId})`} />
      {/* Hairline border */}
      <rect width="40" height="40" rx="10" fill="none" stroke="white" strokeOpacity="0.14" strokeWidth="1" />

      {/* ── M letterform ─────────────────────────────────────── */}
      {/* Two tall verticals joined at top by a V — clean geometric M */}
      <path
        d="M 6 33 L 6 9 L 16 20 L 26 9 L 26 33"
        stroke="white"
        strokeWidth="3.1"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* ── Voice signal bars (right side) ───────────────────── */}
      {/* Short bar */}
      <line x1="30.5" y1="33" x2="30.5" y2="27" stroke="white" strokeWidth="2.6" strokeLinecap="round" strokeOpacity="0.50" />
      {/* Tall bar (primary — full brightness) */}
      <line x1="34.5" y1="33" x2="34.5" y2="13" stroke="white" strokeWidth="2.6" strokeLinecap="round" />
      {/* Medium bar */}
      <line x1="38.5" y1="33" x2="38.5" y2="21" stroke="white" strokeWidth="2.6" strokeLinecap="round" strokeOpacity="0.75" />
    </svg>
  );
}

/**
 * LogoFull — icon badge + wordmark, horizontal layout.
 * size controls the badge height; text scales proportionally.
 */
export function LogoFull({
  size = 36,
  className = "",
  textClassName = "",
}: {
  size?: number;
  className?: string;
  textClassName?: string;
}) {
  const textSize    = Math.round(size * 0.38);   // ~14px at size=36
  const subTextSize = Math.round(size * 0.26);   // ~9px at size=36
  const gap         = Math.round(size * 0.28);   // ~10px at size=36

  return (
    <div className={`inline-flex items-center ${className}`} style={{ gap }}>
      <LogoMark size={size} />
      <div className={textClassName}>
        <div
          style={{
            fontSize: textSize,
            fontWeight: 700,
            letterSpacing: "-0.5px",
            lineHeight: 1,
            fontFamily: "var(--font-sans)",
            background: "linear-gradient(135deg, #fff 30%, oklch(0.78 0.18 268))",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}
        >
          MOTM<span style={{ fontWeight: 300 }}>Voice</span>
        </div>
        <div
          style={{
            fontSize: subTextSize,
            fontWeight: 600,
            letterSpacing: "0.06em",
            marginTop: 2,
            fontFamily: "var(--font-sans)",
            color: "oklch(0.68 0.16 270)",
          }}
        >
          AI Voice Platform
        </div>
      </div>
    </div>
  );
}
