import { useState } from "react";
import { Link } from "react-router-dom";
import { Check, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { usePublicPlans } from "@/lib/hooks";
import type { PublicPlan } from "@/lib/types";
import { cn } from "@/lib/utils";

const SALES_EMAIL = "sales@talkryn.com";

interface FeatureCategory {
  label: string;
  items: string[];
}

// Display-only feature bullets, grouped and keyed by plan name. Falls back
// to plan.marketing_bullets (ungrouped) for any plan name not listed here.
// The first two categories render open by default; the rest sit behind a
// "+N more features" toggle so card heights stay balanced across the row.
const PLAN_FEATURE_CATEGORIES: Record<string, FeatureCategory[]> = {
  Starter: [
    {
      label: "Capacity",
      items: ["500 AI call-minutes every month"],
    },
    {
      label: "AI Features",
      items: [
        "24/7 inbound call handling",
        "AI-powered outbound calling",
        "Personalized voice cloning for your agent",
        "Multilingual conversations — Hinglish, English & more",
      ],
    },
    {
      label: "Insights & Analytics",
      items: ["Call recordings & transcripts"],
    },
    {
      label: "Support & Compliance",
      items: ["CSV & contact import", "Built-in Do-Not-Call compliance"],
    },
  ],
  Professional: [
    {
      label: "Capacity",
      items: ["1,600 AI call-minutes every month"],
    },
    {
      label: "AI Features",
      items: [
        "24/7 inbound call handling",
        "AI-powered outbound calling",
        "Personalized voice cloning for your agent",
        "Multilingual conversations — Hinglish, English & more",
        "Auto-retry on unanswered calls",
        "AI script builder & prompt optimization",
      ],
    },
    {
      label: "Insights & Analytics",
      items: [
        "Call recordings, transcripts & AI summaries",
        "Sentiment analysis on every call",
        "Campaign analytics dashboard",
      ],
    },
    {
      label: "Support & Compliance",
      items: ["CSV & contact import", "Built-in Do-Not-Call compliance", "Priority support"],
    },
  ],
  Enterprise: [
    {
      label: "Capacity",
      items: ["3,200 AI call-minutes every month"],
    },
    {
      label: "AI Features",
      items: [
        "24/7 inbound call handling",
        "AI-powered outbound calling",
        "Personalized voice cloning for your agent",
        "Multilingual conversations — Hinglish, English & more",
        "Auto-retry on unanswered calls",
        "AI script builder & prompt optimization",
        "Scheduled & automated campaign launches",
      ],
    },
    {
      label: "Insights & Analytics",
      items: [
        "Call recordings, transcripts & AI summaries",
        "Sentiment analysis on every call",
        "Advanced, real-time campaign analytics",
      ],
    },
    {
      label: "Support & Compliance",
      items: [
        "Role-based team access & permissions",
        "CSV & contact import",
        "Built-in Do-Not-Call compliance",
        "Dedicated onboarding & priority SLA support",
      ],
    },
  ],
  Business: [
    {
      label: "Capacity",
      items: ["Custom call-minute volume"],
    },
    {
      label: "AI Features",
      items: [
        "24/7 inbound call handling",
        "AI-powered outbound calls",
        "Personalized voice cloning for your agent",
        "AI training & knowledge base",
        "AI script builder",
        "Auto-retry on unanswered calls",
        "Schedule & launch campaigns anytime",
      ],
    },
    {
      label: "Insights & Analytics",
      items: ["Call recordings & transcripts", "AI summaries & sentiment analysis", "Campaign analytics"],
    },
    {
      label: "Support & Compliance",
      items: [
        "CSV & contact import",
        "Dedicated account manager & custom SLA",
        "Custom integrations for your workflow",
      ],
    },
  ],
};

const DEFAULT_VISIBLE_CATEGORIES = 2;

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
  const [showAll, setShowAll] = useState(false);

  const categories = PLAN_FEATURE_CATEGORIES[plan.name];
  const flatBullets = plan.marketing_bullets;
  const hasContent = categories ? categories.some((c) => c.items.length > 0) : flatBullets.length > 0;

  const visibleCategories = categories
    ? showAll
      ? categories
      : categories.slice(0, DEFAULT_VISIBLE_CATEGORIES)
    : [];
  const hiddenFeatureCount = categories
    ? categories.slice(DEFAULT_VISIBLE_CATEGORIES).reduce((sum, c) => sum + c.items.length, 0)
    : 0;

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

        {hasContent && (
          <div className="flex-1 space-y-5">
            {categories
              ? visibleCategories.map((category) => (
                  <div key={category.label}>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                      {category.label}
                    </p>
                    <ul className="mt-2.5 space-y-2.5">
                      {category.items.map((bullet) => (
                        <FeatureBullet key={bullet} bullet={bullet} />
                      ))}
                    </ul>
                  </div>
                ))
              : (
                  <ul className="space-y-2.5">
                    {flatBullets.map((bullet) => (
                      <FeatureBullet key={bullet} bullet={bullet} />
                    ))}
                  </ul>
                )}

            {hiddenFeatureCount > 0 && (
              <button
                type="button"
                onClick={() => setShowAll((v) => !v)}
                className="flex items-center gap-1 text-sm font-medium text-primary transition-colors hover:text-primary/80"
              >
                {showAll ? "Show less" : `+ ${hiddenFeatureCount} more features`}
                <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", showAll && "rotate-180")} />
              </button>
            )}
          </div>
        )}

        <div className={hasContent ? "" : "flex-1"} />

        {plan.is_custom_pricing ? (
          <Button variant="outline" className="w-full" asChild>
            <a
              href={`mailto:${SALES_EMAIL}?subject=${encodeURIComponent(`QuickHowl ${plan.name} Plan Inquiry`)}`}
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
