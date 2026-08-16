import { Check } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { usePublicPlans } from "@/lib/hooks";
import type { PublicPlan } from "@/lib/types";

function formatPrice(priceMinor: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(
    priceMinor / 100
  );
}

// Must match GST_RATE in backend/app/core/razorpay_client.py -- that's what
// actually gets charged (baked into the Razorpay Plan resource at checkout).
// This is purely so the price shown here isn't a surprise once Razorpay's
// own checkout modal opens with the real, GST-inclusive amount.
const GST_RATE = 0.18;

export function PlanPicker({
  selectedPlanId,
  onSelect,
  excludePlanId,
}: {
  selectedPlanId: string | null;
  onSelect: (plan: PublicPlan) => void;
  excludePlanId?: string;
}) {
  const plans = usePublicPlans();
  // Custom-pricing (Business/Contact Sales) plans have no fixed price to
  // check out with — those stay mailto-only, same as the marketing page.
  const selectable = (plans.data ?? []).filter((p) => !p.is_custom_pricing && p.id !== excludePlanId);

  if (plans.isLoading) {
    return (
      <div className="grid gap-3 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {selectable.map((plan) => {
        const selected = plan.id === selectedPlanId;
        const effectivePrice = plan.discount_price_minor ?? plan.price_minor;
        const priceWithGst = Math.round(effectivePrice * (1 + GST_RATE));
        return (
          <Card
            key={plan.id}
            role="button"
            tabIndex={0}
            onClick={() => onSelect(plan)}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(plan)}
            className={cn(
              "cursor-pointer p-4 transition-colors",
              selected ? "border-primary shadow-[var(--shadow-glow)]" : "hover:border-primary/40"
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <p className="font-medium">{plan.name}</p>
              {plan.is_highlighted && (
                <Badge variant="info" className="text-[11px]">Popular</Badge>
              )}
              {selected && <Check className="h-4 w-4 text-primary" />}
            </div>
            <p className="mt-1.5 font-heading text-xl font-semibold">
              {formatPrice(priceWithGst, plan.currency)}
              <span className="text-xs font-normal text-muted-foreground">/mo</span>
            </p>
            <p className="text-xs text-muted-foreground">incl. 18% GST</p>
            <p className="text-xs text-muted-foreground">{plan.credits_per_month.toLocaleString()} min/month</p>
          </Card>
        );
      })}
    </div>
  );
}
