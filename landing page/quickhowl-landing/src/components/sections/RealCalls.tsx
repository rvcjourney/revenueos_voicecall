import { PhoneCall } from "lucide-react";

// Drop the 3 mp3 files into public/audio/ using exactly these filenames —
// files in public/ are served from the site root, so call-1.mp3 here maps
// straight to https://quickhowl.com/audio/call-1.mp3, no build step needed.
const recordings = [
  { file: "/audio/call-1.mp3", label: "Cold outbound call", description: "Opening a conversation with a new lead" },
  { file: "/audio/call-2.mp3", label: "Appointment booking", description: "Qualifying interest and locking in a time" },
  { file: "/audio/call-3.mp3", label: "Objection handling", description: "Responding naturally to pushback" },
];

export function RealCalls() {
  return (
    <section className="section-pad border-t border-border/60">
      <div className="reveal-on-scroll mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow text-primary">Hear it yourself</p>
          <h2 className="mt-3 font-heading text-3xl font-semibold sm:text-4xl">Real calls, not a scripted demo</h2>
          <p className="mt-3 text-muted-foreground">
            Actual recordings from QuickHowl agents talking to real leads — judge the voice quality for yourself.
          </p>
        </div>

        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {recordings.map((r) => (
            <div key={r.file} className="rounded-2xl border border-border bg-card p-6 shadow-[var(--shadow-card)]">
              <span className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/30 bg-primary/15 text-primary">
                <PhoneCall className="h-4 w-4" />
              </span>
              <h4 className="mt-4 text-base font-semibold">{r.label}</h4>
              <p className="mt-1 text-sm text-muted-foreground">{r.description}</p>
              <audio controls preload="none" className="mt-4 w-full" src={r.file}>
                Your browser doesn't support inline audio — download it instead.
              </audio>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
