import { useEffect, useState } from "react";
import { ArrowRight, Check, Mic } from "lucide-react";
import { AIAvatar } from "@/components/shared/AIAvatar";
import { SoundWave } from "@/components/shared/SoundWave";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SIGNUP_URL } from "@/lib/env";

export function Hero() {
  // Purely cosmetic — ticks the demo card's "Live" badge forward from 02:14
  // so the hero mock reads as an in-progress call, not a screenshot.
  const [demoElapsedSeconds, setDemoElapsedSeconds] = useState(134);
  useEffect(() => {
    const id = window.setInterval(() => setDemoElapsedSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, []);
  const demoTimeLabel = `${Math.floor(demoElapsedSeconds / 60)}:${String(demoElapsedSeconds % 60).padStart(2, "0")}`;

  return (
    <section id="top" className="relative overflow-hidden">
      <div className="hero-blob" />
      <div className="dot-grid absolute inset-0" />
      <div className="relative mx-auto grid max-w-7xl grid-cols-1 gap-10 px-4 py-14 sm:px-6 lg:grid-cols-2 lg:items-center lg:px-8 lg:py-20">
        <div className="animate-fade-up min-w-0 space-y-5">
          <Badge variant="success" className="max-w-full">
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current animate-pulse-glow" />
            <span className="min-w-0 whitespace-normal">Live now — 1,200+ AI sales calls running across timezones</span>
          </Badge>
          <h1 className="font-heading text-4xl font-semibold leading-[1.1] sm:text-5xl lg:text-6xl">
            Your AI sales team that <span className="text-gradient">never stops dialing</span>
          </h1>
          <p className="font-heading text-xl font-semibold leading-tight text-foreground sm:text-2xl">
            <Mic className="mr-1.5 inline h-5 w-5 -translate-y-0.5 text-primary" />
            ...and sounds exactly like <span className="text-gradient">you</span>.
          </p>
          <p className="max-w-lg text-lg text-muted-foreground">
            Human-sounding voice agents that call, qualify, and follow up with leads in Hinglish,
            English, and 20+ languages — real conversations and live analytics, without adding a
            single new hire. Clone your own voice, a top rep's, or your founder's once, then reuse
            it across every AI agent.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button size="lg" variant="gradient" className="rounded-full" asChild>
              <a href={SIGNUP_URL}>
                Start free trial <ArrowRight className="h-4 w-4" />
              </a>
            </Button>
            <Button size="lg" variant="outline" className="rounded-full" asChild>
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

        <div className="min-w-0 space-y-4">
          <div className="animate-fade-up glass relative rounded-2xl p-5" style={{ animationDelay: "0.15s" }}>
            <div className="flex items-center justify-between border-b border-border/60 pb-3">
              <div className="flex items-center gap-3">
                <AIAvatar size="sm" />
                <div>
                  <p className="text-sm font-medium">Aniket — AI Agent</p>
                  <p className="text-xs text-muted-foreground">Speaking with Rajesh Sharma</p>
                </div>
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

          <div className="animate-fade-up glass relative rounded-2xl p-5" style={{ animationDelay: "0.3s" }}>
            <div className="flex items-center justify-between border-b border-border/60 pb-3">
              <div className="flex items-center gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
                  <Mic className="h-4 w-4" />
                </span>
                <div>
                  <p className="text-sm font-medium">Voice Cloning</p>
                  <p className="text-xs text-muted-foreground">Founder's voice — 42s sample</p>
                </div>
              </div>
              <Badge variant="success">
                <Check className="h-3 w-3" /> Cloned
              </Badge>
            </div>
            <div className="flex justify-center py-4">
              <SoundWave />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-foreground">Now speaking as:</span>
              <Badge variant="outline">Aniket</Badge>
              <Badge variant="outline">Priya</Badge>
              <Badge variant="outline">+12 more agents</Badge>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
