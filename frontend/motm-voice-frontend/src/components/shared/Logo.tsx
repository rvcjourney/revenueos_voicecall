import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" className={cn("h-8 w-8", className)} aria-hidden>
      <rect width="32" height="32" rx="9" fill="url(#talkryn-logo-gradient)" />
      <rect x="5.6" y="11.5" width="2.4" height="9" rx="1.2" fill="white" fillOpacity="0.85" />
      <rect x="10.2" y="8.5" width="2.4" height="15" rx="1.2" fill="white" />
      <rect x="14.8" y="5.5" width="2.4" height="21" rx="1.2" fill="white" />
      <rect x="19.4" y="7.5" width="2.4" height="17" rx="1.2" fill="white" />
      <rect x="24" y="10.5" width="2.4" height="11" rx="1.2" fill="white" fillOpacity="0.85" />
      <defs>
        <linearGradient id="talkryn-logo-gradient" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop stopColor="oklch(0.6 0.2 280)" />
          <stop offset="1" stopColor="oklch(0.68 0.16 320)" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export function Logo({ className, iconClassName }: { className?: string; iconClassName?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-heading text-lg font-semibold tracking-tight", className)}>
      <LogoMark className={iconClassName} />
      <span>
        Talk<span className="text-gradient">ryn</span>
      </span>
    </span>
  );
}
