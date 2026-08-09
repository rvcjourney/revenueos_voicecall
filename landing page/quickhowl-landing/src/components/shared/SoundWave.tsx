import { cn } from "@/lib/utils";

const HEIGHTS = [40, 70, 100, 55, 85, 35, 95, 60, 45, 75, 50, 90, 65, 30, 80];

export function SoundWave({ className, bars = HEIGHTS }: { className?: string; bars?: number[] }) {
  return (
    <div className={cn("flex h-10 items-center gap-[3px]", className)}>
      {bars.map((h, i) => (
        <span
          key={i}
          className="w-[3px] rounded-full bg-[image:var(--gradient-primary)] animate-wave"
          style={{
            height: `${h}%`,
            animationDelay: `${(i % 6) * 0.12}s`,
          }}
        />
      ))}
    </div>
  );
}
