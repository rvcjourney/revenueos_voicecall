export function SoundWave({ bars = 24, className = "" }: { bars?: number; className?: string }) {
  return (
    <div className={`flex items-center justify-center gap-1 h-16 ${className}`}>
      {Array.from({ length: bars }).map((_, i) => (
        <span
          key={i}
          className="wave-bar w-1.5 rounded-full bg-gradient-primary"
          style={{
            height: `${20 + (i % 5) * 12}px`,
            animationDelay: `${(i * 80) % 800}ms`,
            animationDuration: `${800 + (i % 4) * 120}ms`,
          }}
        />
      ))}
    </div>
  );
}
