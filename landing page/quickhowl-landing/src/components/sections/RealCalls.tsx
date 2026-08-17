import { CircleAudioPlayer } from "@/components/shared/CircleAudioPlayer";

// Add more by dropping an mp3 into public/audio/ and adding an entry here —
// files in public/ are served from the site root, so call-2.mp3 here would
// map straight to https://quickhowl.com/audio/call-2.mp3, no build step needed.
const recordings = [
  { file: "/audio/call-1.mp3", label: "Live QuickHowl AI agent call", description: "Unscripted — judge the voice quality for yourself" },
];

export function RealCalls() {
  return (
    <section className="section-pad border-t border-border/60">
      <div className="reveal-on-scroll mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow text-primary">Hear it yourself</p>
          <h2 className="mt-3 font-heading text-3xl font-semibold sm:text-4xl">A real call, not a scripted demo</h2>
          <p className="mt-3 text-muted-foreground">
            An actual recording of a QuickHowl AI agent on a live call — no cherry-picked script.
          </p>
        </div>

        <div className={`mt-12 grid gap-6 ${recordings.length > 1 ? "md:grid-cols-3" : "mx-auto max-w-md"}`}>
          {recordings.map((r) => (
            <div
              key={r.file}
              className="flex flex-col items-center rounded-2xl border border-border bg-card p-8 text-center shadow-[var(--shadow-card)]"
            >
              <CircleAudioPlayer src={r.file} />
              <h4 className="mt-5 text-base font-semibold">{r.label}</h4>
              <p className="mt-1 text-sm text-muted-foreground">{r.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
