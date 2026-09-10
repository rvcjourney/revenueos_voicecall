import { Download, Mic, Rocket, SlidersHorizontal, Upload } from "lucide-react";
import { cn } from "@/lib/utils";

const steps = [
  { icon: Upload, step: "01", title: "Upload Contacts", description: "Drag in a CSV or Excel file with thousands of leads — we handle column mapping automatically." },
  { icon: Mic, step: "02", title: "Clone Your Voice", description: "Record 60 seconds of your own voice, a top rep's, or your founder's — clone it once, then reuse it on any agent." },
  { icon: SlidersHorizontal, step: "03", title: "Configure Agent", description: "Pick any voice — including one you've cloned — a language, and write (or let AI optimize) a system prompt in minutes." },
  { icon: Rocket, step: "04", title: "Launch Campaign", description: "Calls go out concurrently, at your pace, inside your calling window — no manual dialing." },
  { icon: Download, step: "05", title: "Export Leads", description: "Download interested leads, callbacks, or full results the moment they're ready — synced to your CRM." },
];

const accents = [
  "border-warning/30 bg-warning/15 text-warning",
  "border-primary/30 bg-primary/15 text-primary",
  "border-info/30 bg-info/15 text-info",
  "border-success/30 bg-success/15 text-success",
  "border-white/15 bg-white/10 text-white",
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="mission-band section-pad">
      <div className="reveal-on-scroll mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow text-primary">How it works</p>
          <h2 className="mt-3 font-heading text-3xl font-semibold text-white sm:text-4xl">
            Upload leads. Start conversations. Close more deals
          </h2>
          <p className="mt-3 text-white/65">
            In just 5 steps, QuickHowl turns your spreadsheet into an automated outbound sales engine&mdash;calling leads,
            qualifying prospects, and booking meetings for your team.
          </p>
        </div>
        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-5">
          {steps.map((s, i) => (
            <div
              key={s.step}
              className="hover-lift reveal-on-scroll rounded-2xl border border-white/10 bg-white/5 p-6"
              style={{ animationDelay: `${i * 0.1}s` }}
            >
              <span className={cn("flex h-10 w-10 items-center justify-center rounded-lg border", accents[i % accents.length])}>
                <s.icon className="h-4 w-4" />
              </span>
              <p className="mt-4 font-heading text-2xl font-bold text-white/25">{s.step}</p>
              <h4 className="mt-1 text-base font-semibold text-white">{s.title}</h4>
              <p className="mt-2 text-sm text-white/62">{s.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
