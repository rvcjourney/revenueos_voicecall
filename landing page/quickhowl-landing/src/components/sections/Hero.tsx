import { ArrowRight, Check, Mic } from "lucide-react";
import { AIAvatar } from "@/components/shared/AIAvatar";
import { SoundWave } from "@/components/shared/SoundWave";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SIGNUP_URL } from "@/lib/env";

export function Hero() {
  return (
    <section id="top" className="relative overflow-hidden">
      <div className="hero-blob" />
      <div className="dot-grid absolute inset-0" />
      <div className="relative mx-auto grid max-w-7xl grid-cols-1 gap-8 px-4 py-10 sm:px-6 lg:grid-cols-2 lg:items-center lg:px-8 lg:py-14">
        <div className="animate-fade-up min-w-0 space-y-3">
          <Badge variant="success" className="max-w-full">
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current animate-pulse-glow" />
            <span className="min-w-0 whitespace-normal">AI voice agents built for Hindi &amp; English sales calls</span>
          </Badge>
          <h1 className="font-heading text-xl font-semibold leading-[1.2] sm:text-2xl lg:text-3xl">
            Your AI sales team that <span className="text-gradient">never stops dialing</span>
          </h1>
          <p className="font-heading text-sm font-semibold leading-tight text-foreground sm:text-base">
            <Mic className="mr-1.5 inline h-3.5 w-3.5 -translate-y-0.5 text-primary" />
            ...and sounds exactly like <span className="text-gradient">you</span>.
          </p>
          <p className="max-w-lg text-sm text-muted-foreground">
            Human-sounding voice agents that call, qualify, and follow up with leads in Hinglish,
            English, and more — real conversations and live analytics, without adding a single new
            hire. Clone your own voice, a top rep's, or your founder's once, then reuse it across
            every AI agent.
          </p>
          <div className="flex flex-wrap gap-3 pt-1">
            <Button size="lg" variant="gradient" className="rounded-full" asChild>
              <a href={SIGNUP_URL}>
                Start free trial <ArrowRight className="h-4 w-4" />
              </a>
            </Button>
            <Button size="lg" variant="outline" className="rounded-full" asChild>
              <a href="#how-it-works">Watch how it works</a>
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5 pt-1 text-xs text-muted-foreground">
            <span>No credit card required</span>
            <span className="hidden h-1 w-1 rounded-full bg-border sm:block" />
            <span>Live in under 10 minutes</span>
            <span className="hidden h-1 w-1 rounded-full bg-border sm:block" />
            <span>Works with any SIP number</span>
          </div>
        </div>

        <div className="min-w-0 space-y-2">
          <div className="animate-fade-up glass relative rounded-2xl p-3" style={{ animationDelay: "0.15s" }}>
            <div className="flex items-center justify-between border-b border-border/60 pb-2">
              <div className="flex items-center gap-2.5">
                <AIAvatar size="sm" />
                <div>
                  <p className="text-sm font-medium">Aniket — AI Agent</p>
                  <p className="text-xs text-muted-foreground">Speaking with Rajesh Sharma</p>
                </div>
              </div>
              <Badge variant="outline">Sample conversation</Badge>
            </div>
            <div className="flex justify-center py-1">
              <SoundWave className="h-7" />
            </div>
            <div className="space-y-2">
              <div
                className="animate-bubble-in rounded-xl rounded-tl-sm bg-muted p-2.5 text-sm"
                style={{ animationDelay: "0.1s" }}
              >
                <p className="mb-0.5 text-xs font-medium text-muted-foreground">Aniket</p>
                "Sir, main samajh sakta hoon budget ek concern hai — same quality mein hum aapko 30%
                kam price de sakte hain. Kal shaam 4 baje ek quick demo fix kar doon?"
              </div>
              <div
                className="animate-bubble-in ml-auto max-w-[85%] rounded-xl rounded-tr-sm bg-primary/15 p-2.5 text-sm"
                style={{ animationDelay: "0.35s" }}
              >
                <p className="mb-0.5 text-xs font-medium text-primary">Rajesh</p>
                "Haan bilkul, kal 4 baje baat kar lete hain."
              </div>
            </div>
            <div className="mt-2 flex justify-end">
              <Badge variant="success" className="animate-bubble-in" style={{ animationDelay: "0.6s" }}>
                <Check className="h-3 w-3" /> Auto-tagged as hot lead
              </Badge>
            </div>
          </div>

          <div className="animate-fade-up glass relative rounded-2xl p-3" style={{ animationDelay: "0.3s" }}>
            <div className="flex items-center justify-between border-b border-border/60 pb-2">
              <div className="flex items-center gap-2.5">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
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
            <div className="flex justify-center py-1">
              <SoundWave className="h-7" />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-foreground">Now speaking as:</span>
              <Badge variant="outline">Aniket</Badge>
              <Badge variant="outline">Priya</Badge>
              <Badge variant="outline">More agent voices</Badge>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
