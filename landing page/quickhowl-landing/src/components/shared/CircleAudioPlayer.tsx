import { useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";

function formatTime(seconds: number) {
  if (!Number.isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// Deliberately no scrubber/progress line -- just a big circular play/pause
// button with a live elapsed-time readout, per founder request.
export function CircleAudioPlayer({ src }: { src: string }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onTimeUpdate = () => setCurrentTime(audio.currentTime);
    const onLoadedMetadata = () => setDuration(audio.duration);
    const onEnded = () => {
      setIsPlaying(false);
      setCurrentTime(0);
    };

    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("loadedmetadata", onLoadedMetadata);
    audio.addEventListener("ended", onEnded);
    return () => {
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("loadedmetadata", onLoadedMetadata);
      audio.removeEventListener("ended", onEnded);
    };
  }, []);

  function toggle() {
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
    } else {
      void audio.play();
      setIsPlaying(true);
    }
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <audio ref={audioRef} src={src} preload="metadata" />
      <button
        type="button"
        onClick={toggle}
        aria-label={isPlaying ? "Pause recording" : "Play recording"}
        className="group relative flex h-20 w-20 items-center justify-center rounded-full"
      >
        {isPlaying && (
          <>
            <span className="absolute inset-0 animate-ping rounded-full bg-primary/30" />
            <span className="absolute inset-0 animate-pulse rounded-full bg-primary/15" style={{ animationDelay: "0.4s" }} />
          </>
        )}
        <span className="relative flex h-20 w-20 items-center justify-center rounded-full bg-[image:var(--gradient-primary)] text-white shadow-[var(--shadow-card)] transition-transform duration-200 group-hover:scale-105 group-active:scale-95">
          {isPlaying ? <Pause className="h-7 w-7" fill="currentColor" /> : <Play className="ml-1 h-7 w-7" fill="currentColor" />}
        </span>
      </button>
      <p className="tabular-nums text-xs font-medium text-muted-foreground">
        {isPlaying || currentTime > 0 ? `${formatTime(currentTime)} / ${formatTime(duration)}` : "Tap to play"}
      </p>
    </div>
  );
}
