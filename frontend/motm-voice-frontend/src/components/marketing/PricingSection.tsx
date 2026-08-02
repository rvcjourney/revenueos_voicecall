import { Link } from "react-router-dom";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { usePublicPlans } from "@/lib/hooks";
import type { PublicPlan } from "@/lib/types";

const SALES_EMAIL = "sales@talkryn.com";

function formatPrice(priceMinor: number, currency: string) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(priceMinor / 100);
}

export function PricingSection() {
  const plans = usePublicPlans();

  return (
    <section id="pricing" className="border-t border-border/60 bg-card/30 py-20">
      <div className="reveal-on-scroll mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="font-heading text-3xl font-semibold sm:text-4xl">Talkryn Plans</h2>
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

  return (
    <Card className={plan.is_highlighted ? "relative border-primary/60 shadow-[var(--shadow-glow)]" : ""}>
      {plan.is_highlighted && (
        <Badge className="absolute -top-3 left-1/2 -translate-x-1/2">Most popular</Badge>
      )}
      <CardContent className="flex h-full flex-col space-y-6 pt-8">
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

        {plan.marketing_bullets.length > 0 && (
          <ul className="flex-1 space-y-2.5">
            {plan.marketing_bullets.map((bullet) => (
              <li key={bullet} className="flex items-center gap-2 text-sm text-muted-foreground">
                <Check className="h-4 w-4 shrink-0 text-success" /> {bullet}
              </li>
            ))}
          </ul>
        )}

        <div className={plan.marketing_bullets.length > 0 ? "" : "flex-1"} />

        {plan.is_custom_pricing ? (
          <Button variant="outline" className="w-full" asChild>
            <a
              href={`mailto:${SALES_EMAIL}?subject=${encodeURIComponent(`Talkryn ${plan.name} Plan Inquiry`)}`}
              aria-label={`Contact sales about the ${plan.name} plan`}
            >
              Contact Sales
            </a>
          </Button>
        ) : (
          <Button variant={plan.is_highlighted ? "gradient" : "outline"} className="w-full" asChild>
            <Link to="/signup" aria-label={`Get started with the ${plan.name} plan`}>
              Get Started
            </Link>
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
