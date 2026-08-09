import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LOGIN_URL, SIGNUP_URL } from "@/lib/env";

export function FinalCTA() {
  return (
    <section className="section-pad border-t border-border/60">
      <div className="reveal-on-scroll mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <div className="gradient-cta-box animate-gradient-pan rounded-[28px] px-8 py-16 text-center sm:px-16">
          <h2 className="font-heading text-3xl font-semibold text-white sm:text-4xl">
            Ready to put your outbound calling on autopilot?
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-white/90">
            Launch your first AI voice campaign today — no credit card, no code, no waiting.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            {/* Always a white pill regardless of theme, so the text color must be
                hardcoded too — `text-foreground` would resolve to near-white in
                dark mode and disappear against this button's white background. */}
            <Button
              size="lg"
              className="rounded-full bg-white text-[oklch(0.18_0.016_275)] hover:bg-white/90"
              asChild
            >
              <a href={SIGNUP_URL}>
                Start free trial <ArrowRight className="h-4 w-4" />
              </a>
            </Button>
            <Button size="lg" variant="outline" className="rounded-full border-white/50 text-white hover:bg-white/10" asChild>
              <a href={LOGIN_URL}>Log in</a>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
