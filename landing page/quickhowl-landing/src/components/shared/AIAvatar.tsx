import { cn } from "@/lib/utils";

const SIZES = {
  sm: { wrap: "h-10 w-10", icon: "h-4 w-4" },
  md: { wrap: "h-16 w-16", icon: "h-6 w-6" },
  lg: { wrap: "h-28 w-28", icon: "h-10 w-10" },
} as const;

interface AIAvatarProps {
  size?: keyof typeof SIZES;
  /** Whether the sonar rings + inner equalizer animate — set false for a static/idle avatar. */
  speaking?: boolean;
  className?: string;
}

// Decorative avatar used wherever we want to visually represent "the AI agent
// is on a call" — e.g. the Landing page hero mock. Purely a looping CSS
// animation (expanding rings + a gentle bob + an equalizer glyph), not driven
// by real audio. Deliberately abstract, not a human photo/face — this stands
// in for an AI agent in marketing copy, not a real person.
export function AIAvatar({ size = "md", speaking = true, className }: AIAvatarProps) {
  const s = SIZES[size];
  return (
    <div className={cn("relative flex shrink-0 items-center justify-center", s.wrap, className)}>
      {speaking && (
        <>
          <span className="absolute inset-0 -z-10 rounded-full bg-[image:var(--gradient-primary)] opacity-50 blur-xl animate-pulse-glow" />
          <span className="absolute inset-0 rounded-full bg-[image:var(--gradient-primary)] animate-avatar-ring" />
          <span
            className="absolute inset-0 rounded-full bg-[image:var(--gradient-primary)] animate-avatar-ring"
            style={{ animationDelay: "0.8s" }}
          />
          <span
            className="absolute inset-0 rounded-full bg-[image:var(--gradient-primary)] animate-avatar-ring"
            style={{ animationDelay: "1.6s" }}
          />
        </>
      )}
      <span
        className={cn(
          "relative flex h-full w-full items-center justify-center rounded-full bg-[image:var(--gradient-primary)] shadow-lg shadow-primary/25",
          speaking && "animate-avatar-bob"
        )}
      >
        {/* Abstract equalizer glyph, not a mic icon — visibly "talks" instead of sitting static */}
        <span className={cn(s.icon, "flex items-end justify-center gap-[2.5px]")}>
          {[65, 100, 65].map((h, i) => (
            <span
              key={i}
              className={cn(
                "w-[2.5px] origin-bottom rounded-full bg-primary-foreground",
                speaking && "animate-wave"
              )}
              style={{ height: `${h}%`, animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </span>
      </span>
    </div>
  );
}
