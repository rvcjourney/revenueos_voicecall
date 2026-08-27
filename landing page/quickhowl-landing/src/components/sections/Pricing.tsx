import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { usePublicPlans } from "@/lib/hooks";
import { SIGNUP_URL } from "@/lib/env";
import type { PublicPlan } from "@/lib/types";
import { cn } from "@/lib/utils";

// Ported from frontend/motm-voice-frontend/src/components/marketing/PricingSection.tsx.
// The source file has a pre-existing brand-name bug in SALES_EMAIL
// ("sales@talkryn.com") — corrected here rather than propagated, per the
// instruction not to carry existing content bugs into new copy.
const SALES_EMAIL = "sales@quickhowl.com";

// Same fixed bullet list on every plan card -- the only thing that changes
// per plan is the call-minutes line, which is generated from the plan's own
// credits_per_month (or "Custom call-minute volume" for custom pricing).
// Deliberately not sourced from plan.marketing_bullets/features anymore.
function planBullets(plan: PublicPlan): string[] {
  const minutesLine = plan.is_custom_pricing
    ? "Custom call-minute volume"
    : `${plan.credits_per_month.toLocaleString()} AI call-minutes every month`;
  return [
    minutesLine,
    "24/7 inbound call handling",
    "AI-powered outbound calling",
    "Personalized voice cloning for your agent",
    "Call recordings & transcripts",
    "CSV & contact import",
  ];
}

function formatPrice(priceMinor: number, currency: string) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(priceMinor / 100);
}

export function Pricing() {
  const plans = usePublicPlans();

  return (
    <section id="pricing" className="section-pad border-t border-border/60 bg-card/30">
      <div className="reveal-on-scroll mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="font-heading text-3xl font-semibold sm:text-4xl">QuickHowl Plans</h2>
          <p className="mt-3 text-muted-foreground">Simple, usage-based pricing that scales with your call volume.</p>
        </div>

        {plans.isLoading ? (
          <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-96 w-full" />
            ))}
          </div>
        ) : plans.isError || !plans.data || plans.data.length === 0 ? null : (
          <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {plans.data.map((plan) => (
              <PricingCard key={plan.id} plan={plan} />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function PricingCard({ plan }: { plan: PublicPlan }) {
  const hasDiscount = plan.discount_price_minor != null;
  const bullets = planBullets(plan);

  return (
    <div
      className={cn(
        "relative flex h-full flex-col rounded-2xl border border-border bg-card p-6 shadow-[var(--shadow-card)]",
        plan.is_highlighted && "border-primary/60 shadow-[var(--shadow-glow)]"
      )}
    >
      {plan.is_highlighted && (
        <Badge className="absolute -top-3 left-1/2 -translate-x-1/2">Most popular</Badge>
      )}
      <div className="flex h-full flex-col space-y-6 pt-2">
        <h3 className="font-medium">{plan.name}</h3>

        <div>
          {plan.is_custom_pricing ? (
            <span className="font-heading text-3xl font-semibold">Custom</span>
          ) : hasDiscount ? (
            <div className="flex items-baseline gap-2">
              <span className="font-heading text-3xl font-semibold">
                {formatPrice(plan.discount_price_minor!, plan.currency)}
              </span>
              <span className="text-sm text-muted-foreground line-through">
                {formatPrice(plan.price_minor, plan.currency)}
              </span>
              <span className="text-sm text-muted-foreground">/month</span>
            </div>
          ) : (
            <div className="flex items-baseline gap-1">
              <span className="font-heading text-3xl font-semibold">{formatPrice(plan.price_minor, plan.currency)}</span>
              <span className="text-sm text-muted-foreground">/month</span>
            </div>
          )}
          <p className="mt-2 text-sm text-muted-foreground">
            {plan.is_custom_pricing ? "Custom volume" : `${plan.credits_per_month.toLocaleString()} min/month`}
          </p>
        </div>

        <div className="flex-1">
          <ul className="space-y-2.5">
            {bullets.map((bullet) => (
              <FeatureBullet key={bullet} bullet={bullet} />
            ))}
          </ul>
        </div>

        {plan.is_custom_pricing ? (
          <Button variant="outline" className="w-full rounded-full" asChild>
            <a
              href={`mailto:${SALES_EMAIL}?subject=${encodeURIComponent(`QuickHowl ${plan.name} Plan Inquiry`)}`}
              aria-label={`Contact sales about the ${plan.name} plan`}
            >
              Contact Sales
            </a>
          </Button>
        ) : (
          <Button variant={plan.is_highlighted ? "gradient" : "outline"} className="w-full rounded-full" asChild>
            <a href={SIGNUP_URL} aria-label={`Get started with the ${plan.name} plan`}>
              Get Started
            </a>
          </Button>
        )}
      </div>
    </div>
  );
}

function FeatureBullet({ bullet }: { bullet: string }) {
  return (
    <li className="flex items-start gap-2.5 text-sm text-muted-foreground">
      <span className="mt-0.5 flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-full bg-success/15">
        <Check className="h-3 w-3 text-success" strokeWidth={3} />
      </span>
      <span>{bullet}</span>
    </li>
  );
}
