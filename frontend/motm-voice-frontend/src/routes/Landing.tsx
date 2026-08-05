import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Languages,
  FileSpreadsheet,
  Gauge,
  LineChart,
  FileText,
  ShieldCheck,
  Users2,
  PhoneForwarded,
  ArrowRight,
  Upload,
  SlidersHorizontal,
  Rocket,
  Download,
  Check,
  Play,
  Pause,
  ArrowDownRight,
} from "lucide-react";
import { PublicNav } from "@/components/marketing/PublicNav";
import { PublicFooter } from "@/components/marketing/PublicFooter";
import { PricingSection } from "@/components/marketing/PricingSection";
import { SoundWave } from "@/components/shared/SoundWave";
import { AIAvatar } from "@/components/shared/AIAvatar";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { cn } from "@/lib/utils";

const features = [
  {
    icon: Languages,
    title: "Human-like multilingual voice",
    description: "Natural, code-switching conversations in Hinglish, English, and 20+ languages — agents that sound like your best rep, not a robot.",
  },
  {
    icon: FileSpreadsheet,
    title: "Bulk contact import",
    description: "Drag in a CSV or Excel file with thousands of leads. Extra columns become custom fields, automatically.",
  },
  {
    icon: Gauge,
    title: "Concurrent batch calling",
    description: "Dial hundreds of numbers at once. Set your pace, calling windows, and days to match your team's bandwidth and compliance needs.",
  },
  {
    icon: FileText,
    title: "Transcripts & AI summaries",
    description: "Every call comes with a full transcript, an AI summary, sentiment tag, and structured extracted data — no manual note-taking.",
  },
  {
    icon: LineChart,
    title: "Live campaign dashboard",
    description: "Watch dialing, completed, failed, and interested counts update in real time as your campaign runs.",
  },
  {
    icon: Download,
    title: "Segmented exports",
    description: "One-click export of interested leads, callbacks, or full results — ready to drop straight into your CRM.",
  },
  {
    icon: ShieldCheck,
    title: "Built-in compliance",
    description: "Org-level Do Not Call lists, plus automatic enforcement against India's TRAI NCPR registry — compliance without the busywork.",
  },
  {
    icon: Users2,
    title: "Role-based team access",
    description: "Admins manage everything; reps request access to the agents they need, with per-agent edit permissions.",
  },
  {
    icon: PhoneForwarded,
    title: "Bring your own number",
    description: "Connect your own SIP trunk with a guided verify-and-test flow — no engineering ticket, no waiting on IT.",
  },
];

const steps = [
  { icon: Upload, step: "01", title: "Upload Contacts", description: "Drag in a CSV or Excel file with thousands of leads — we handle column mapping automatically." },
  { icon: SlidersHorizontal, step: "02", title: "Configure Agent", description: "Pick a voice, a language, and write (or let AI optimize) a system prompt in minutes." },
  { icon: Rocket, step: "03", title: "Launch Campaign", description: "Calls go out concurrently, at your pace, inside your calling window — no manual dialing." },
  { icon: Download, step: "04", title: "Export Leads", description: "Download interested leads, callbacks, or full results the moment they're ready — synced to your CRM." },
];

const stepAccents = [
  "border-warning/30 bg-warning/10 text-warning",
  "border-primary/30 bg-primary/10 text-primary",
  "border-info/30 bg-info/10 text-info",
  "border-success/30 bg-success/10 text-success",
];

const stepStagger = ["lg:ml-0", "lg:ml-12", "lg:ml-24", "lg:ml-36"];

const faqs = [
  {
    q: "Is this compliant with India's calling regulations?",
    a: "Yes. Every organization gets its own Do Not Call list, and all numbers are automatically checked against India's TRAI NCPR (National Customer Preference Register) before dialing.",
  },
  {
    q: "Do the AI agents actually sound natural in Hindi-English mixed conversations?",
    a: "The default agent language is Hinglish — code-mixed Hindi/English speech-to-text and text-to-speech tuned for natural, code-switching conversation, alongside 20+ other languages.",
  },
  {
    q: "Can I use this outside India?",
    a: "Yes. While Hinglish is our specialty, agents support 20+ languages and connect to any SIP-based number worldwide — teams outside India use it for English-only outbound too.",
  },
  {
    q: "Can I use my own phone number?",
    a: "Yes. Connect your own SIP trunk through a guided self-serve flow: add your credentials, run a live test call, and you're ready to dial.",
  },
  {
    q: "What happens if a call reaches voicemail or an automated phone tree?",
    a: "The agent detects voicemail greetings and IVR/phone-tree prompts and hangs up instantly, so you're not billed for dead air.",
  },
  {
    q: "Can my sales reps use this without full admin access?",
    a: "Yes. Members get a restricted view — their own campaigns only — and must request access to each AI agent before using it, which an admin approves.",
  },
];

export default function Landing() {
  const demoAudioRef = useRef<HTMLAudioElement>(null);
  const [isDemoPlaying, setIsDemoPlaying] = useState(false);

  const toggleDemoAudio = () => {
    const audio = demoAudioRef.current;
    if (!audio) return;
    if (isDemoPlaying) {
      audio.pause();
    } else {
      audio.play().catch(() => {});
    }
  };

  // Purely cosmetic — ticks the demo card's "Live" badge forward from 02:14
  // so the hero mock reads as an in-progress call, not a screenshot.
  const [demoElapsedSeconds, setDemoElapsedSeconds] = useState(134);
  useEffect(() => {
    const id = window.setInterval(() => setDemoElapsedSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, []);
  const demoTimeLabel = `${Math.floor(demoElapsedSeconds / 60)}:${String(demoElapsedSeconds % 60).padStart(2, "0")}`;

  return (
    <div className="min-h-screen overflow-x-hidden bg-background">
      <PublicNav />

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="dot-grid absolute inset-0" />
        <div className="relative mx-auto grid max-w-7xl grid-cols-1 gap-10 px-4 py-10 sm:px-6 lg:grid-cols-2 lg:items-center lg:px-8 lg:py-14">
          <div className="animate-fade-up min-w-0 space-y-5">
            <Badge variant="success" className="max-w-full">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current animate-pulse-glow" />
              <span className="min-w-0 whitespace-normal">Live now — 1,200+ AI sales calls running across timezones</span>
            </Badge>
            <h1 className="font-heading text-4xl font-semibold leading-[1.1] sm:text-5xl lg:text-6xl">
              Your AI sales team that <span className="text-gradient">never stops dialing</span>
            </h1>
            <p className="max-w-lg text-lg text-muted-foreground">
              Human-sounding voice agents that call, qualify, and follow up with leads in Hinglish,
              English, and 20+ languages — real conversations and live analytics, without adding a
              single new hire.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button size="lg" variant="gradient" asChild>
                <Link to="/signup">
                  Start free trial <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <a href="#how-it-works">Watch how it works</a>
              </Button>
            </div>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5 pt-2 text-xs text-muted-foreground">
              <span>No credit card required</span>
              <span className="hidden h-1 w-1 rounded-full bg-border sm:block" />
              <span>Live in under 10 minutes</span>
              <span className="hidden h-1 w-1 rounded-full bg-border sm:block" />
              <span>Works with any SIP number</span>
            </div>
          </div>

          <div className="animate-fade-up glass relative rounded-2xl p-5" style={{ animationDelay: "0.15s" }}>
            <div className="flex items-center justify-between border-b border-border/60 pb-3">
              <div className="flex items-center gap-3">
                <AIAvatar size="sm" />
                <div>
                  <p className="text-sm font-medium">Aniket — AI Agent</p>
                  <p className="text-xs text-muted-foreground">Speaking with Rajesh Sharma</p>
                </div>
                <button
                  type="button"
                  onClick={toggleDemoAudio}
                  aria-label={isDemoPlaying ? "Pause call recording" : "Play call recording"}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-muted text-foreground transition-all hover:scale-110 hover:bg-accent active:scale-90"
                >
                  {isDemoPlaying ? (
                    <Pause className="h-3.5 w-3.5" />
                  ) : (
                    <Play className="h-3.5 w-3.5 translate-x-[1px]" />
                  )}
                </button>
                <audio
                  ref={demoAudioRef}
                  src="/demo-call.mp3"
                  onPlay={() => setIsDemoPlaying(true)}
                  onPause={() => setIsDemoPlaying(false)}
                  onEnded={() => setIsDemoPlaying(false)}
                  className="hidden"
                />
              </div>
              <Badge variant="success">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-75" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
                </span>
                Live {demoTimeLabel}
              </Badge>
            </div>
            <div className="flex justify-center py-4">
              <SoundWave />
            </div>
            <div className="space-y-3">
              <div
                className="animate-bubble-in rounded-xl rounded-tl-sm bg-muted p-3 text-sm"
                style={{ animationDelay: "0.1s" }}
              >
                <p className="mb-1 text-xs font-medium text-muted-foreground">Aniket</p>
                "Sir, main samajh sakta hoon budget ek concern hai — same quality mein hum aapko 30%
                kam price de sakte hain. Kal shaam 4 baje ek quick demo fix kar doon?"
              </div>
              <div
                className="animate-bubble-in ml-auto max-w-[85%] rounded-xl rounded-tr-sm bg-primary/15 p-3 text-sm"
                style={{ animationDelay: "0.35s" }}
              >
                <p className="mb-1 text-xs font-medium text-primary">Rajesh</p>
                "Haan bilkul, kal 4 baje baat kar lete hain."
              </div>
            </div>
            <div className="mt-4 flex justify-end">
              <Badge variant="success" className="animate-bubble-in" style={{ animationDelay: "0.6s" }}>
                <Check className="h-3 w-3" /> Auto-tagged as hot lead
              </Badge>
            </div>
          </div>
        </div>
      </section>

      {/* Industries */}
      <section className="border-t border-border/60 py-10">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
          <p className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Built for outbound teams across industries
          </p>
          <div className="mt-5 flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-sm text-muted-foreground">
            <span>B2B SaaS</span>
            <span>Real Estate</span>
            <span>Fintech</span>
            <span>Healthcare</span>
            <span>EdTech</span>
            <span>D2C & Retail</span>
            <span>Insurance</span>
            <span>Financial Services</span>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="border-t border-border/60 py-20">
        <div className="reveal-on-scroll mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="font-heading text-3xl font-semibold sm:text-4xl">From spreadsheet to closed deals in 4 steps</h2>
            <p className="mt-3 text-muted-foreground">No dialer to configure, no scripts to memorize — just upload your list and launch in minutes.</p>
          </div>
          <div className="mt-16 mx-auto max-w-md lg:max-w-2xl">
            {steps.map((s, i) => (
              <div key={s.step}>
                <div
                  className={cn(
                    "w-full max-w-sm rounded-2xl border p-5 transition-transform hover:-translate-y-0.5",
                    stepAccents[i % stepAccents.length],
                    stepStagger[i % stepStagger.length]
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-background/60">
                      <s.icon className="h-4 w-4" />
                    </span>
                    <span className="font-heading text-3xl font-bold opacity-25">{s.step}</span>
                  </div>
                  <p className="mt-3 text-base font-semibold text-foreground">{s.title}</p>
                </div>
                <p
                  className={cn(
                    "mt-2 max-w-sm text-sm text-muted-foreground",
                    stepStagger[i % stepStagger.length]
                  )}
                >
                  {s.description}
                </p>
                {i < steps.length - 1 && (
                  <div className={cn("flex py-3", stepStagger[i % stepStagger.length])}>
                    <ArrowDownRight className="h-5 w-5 text-muted-foreground/40" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="border-t border-border/60 bg-card/30 py-20">
        <div className="reveal-on-scroll mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="font-heading text-3xl font-semibold sm:text-4xl">Everything your outbound team needs to scale</h2>
            <p className="mt-3 text-muted-foreground">One platform for calling, compliance, and conversion — built for high-volume B2B sales teams.</p>
          </div>
          <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((f) => (
              <Card key={f.title}>
                <CardContent className="space-y-3 pt-6">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 text-primary">
                    <f.icon className="h-5 w-5" />
                  </span>
                  <p className="font-medium">{f.title}</p>
                  <p className="text-sm text-muted-foreground">{f.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="border-t border-border/60 py-20">
        <div className="reveal-on-scroll mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="font-heading text-3xl font-semibold sm:text-4xl">Loved by sales teams scaling outbound, everywhere</h2>
          </div>
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {[
              {
                quote: "We 4x'd our outbound reach without hiring a single extra SDR — and the Hinglish agent genuinely sounds like a person.",
                name: "VP of Sales",
                org: "B2B SaaS company",
              },
              {
                quote: "Setup took an afternoon. Within a week we had a full pipeline of interested leads flowing straight into our CRM.",
                name: "RevOps Manager",
                org: "Manufacturing distributor",
              },
              {
                quote: "Built-in DNC and TRAI compliance gave our legal team the confidence to greenlight this immediately — no back-and-forth.",
                name: "Head of Growth",
                org: "Fintech startup",
              },
            ].map((t) => (
              <Card key={t.name}>
                <CardContent className="space-y-4 pt-6">
                  <p className="text-sm leading-relaxed text-foreground/90">"{t.quote}"</p>
                  <div>
                    <p className="text-sm font-medium">{t.name}</p>
                    <p className="text-xs text-muted-foreground">{t.org}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <PricingSection />

      {/* FAQ */}
      <section id="faq" className="border-t border-border/60 py-20">
        <div className="reveal-on-scroll mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
          <h2 className="text-center font-heading text-3xl font-semibold sm:text-4xl">Frequently asked questions</h2>
          <Accordion type="single" collapsible className="mt-10">
            {faqs.map((f) => (
              <AccordionItem key={f.q} value={f.q}>
                <AccordionTrigger>{f.q}</AccordionTrigger>
                <AccordionContent>{f.a}</AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>
      </section>

      {/* Final CTA */}
      <section className="border-t border-border/60 py-20">
        <div className="reveal-on-scroll mx-auto max-w-4xl px-4 text-center sm:px-6 lg:px-8">
          <h2 className="font-heading text-3xl font-semibold sm:text-4xl">Ready to put your outbound calling on autopilot?</h2>
          <p className="mt-3 text-muted-foreground">Launch your first AI voice campaign today — no credit card, no code, no waiting.</p>
          <div className="mt-8 flex justify-center gap-3">
            <Button size="lg" variant="gradient" asChild>
              <Link to="/signup">
                Start free trial <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button size="lg" variant="outline" asChild>
              <Link to="/login">Log in</Link>
            </Button>
          </div>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
