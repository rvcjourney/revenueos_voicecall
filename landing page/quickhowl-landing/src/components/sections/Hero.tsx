import { ArrowRight, Mic } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SIGNUP_URL } from "@/lib/env";

export function Hero() {
  return (
    <section id="top" className="relative overflow-hidden">
      <div className="hero-blob" />
      <div className="dot-grid absolute inset-0" />
      <div className="animate-fade-up relative mx-auto max-w-4xl px-4 py-14 text-center sm:px-6 lg:px-8 lg:py-20">
        <Badge variant="success" className="mx-auto max-w-full">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current animate-pulse-glow" />
          <span className="min-w-0 whitespace-normal">AI voice agents built for Hindi &amp; English sales calls</span>
        </Badge>
        <h1 className="font-heading mt-4 text-2xl font-semibold leading-[1.2] sm:text-3xl lg:text-4xl">
          Your AI sales team that <span className="text-gradient">never stops dialing</span>
        </h1>
        <p className="font-heading mt-3 text-base font-semibold leading-tight text-foreground sm:text-lg">
          <Mic className="mr-1.5 inline h-4 w-4 -translate-y-0.5 text-primary" />
          ...and sounds exactly like <span className="text-gradient">you</span>.
        </p>
        <p className="mx-auto mt-3 max-w-lg text-sm text-muted-foreground sm:text-base">
          Human-sounding voice agents that call, qualify, and follow up with leads in Hinglish,
          English, and more — real conversations and live analytics, without adding a single new
          hire. Clone your own voice, a top rep's, or your founder's once, then reuse it across
          every AI agent.
        </p>
        <div className="mt-5 flex flex-wrap justify-center gap-3">
          <Button size="lg" variant="gradient" className="rounded-full" asChild>
            <a href={SIGNUP_URL}>
              Start free trial <ArrowRight className="h-4 w-4" />
            </a>
          </Button>
          <Button size="lg" variant="outline" className="rounded-full" asChild>
            <a href="#how-it-works">Watch how it works</a>
          </Button>
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-center gap-x-6 gap-y-1.5 text-xs text-muted-foreground">
          <span>No credit card required</span>
          <span className="hidden h-1 w-1 rounded-full bg-border sm:block" />
          <span>Live in under 10 minutes</span>
          <span className="hidden h-1 w-1 rounded-full bg-border sm:block" />
          <span>Works with any SIP number</span>
        </div>
      </div>
    </section>
  );
}
