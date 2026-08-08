import { useState } from "react";
import { toast } from "sonner";
import {
  Building2,
  CalendarClock,
  CheckCircle2,
  Circle,
  CreditCard,
  ListChecks,
  Loader2,
  Receipt,
  ShieldCheck,
  Sparkles,
  Zap,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { PlanPicker } from "@/components/billing/PlanPicker";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { apiErrorMessage } from "@/lib/api";
import { useBillingCurrent, useCheckout, useCreditUsage, useVerifyPayment } from "@/lib/hooks";
import { openRazorpayCheckout } from "@/lib/razorpayCheckout";
import type { PublicPlan } from "@/lib/types";

function notImplemented(action: string) {
  toast.info(`${action} isn't connected yet — this is a UI preview only.`);
}

function formatPrice(priceMinor: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(
    priceMinor / 100
  );
}

export default function Billing() {
  const { user } = useAuth();
  const credits = useCreditUsage();
  const billing = useBillingCurrent();
  const pct = credits.data ? Math.min((credits.data.used / Math.max(credits.data.allotted, 1)) * 100, 100) : 0;

  const plan = billing.data?.plan;
  const effectivePriceMinor = plan ? plan.discount_price_minor ?? plan.price_minor : null;
  const renewsOn = billing.data?.current_period_end
    ? new Date(billing.data.current_period_end).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : null;
  const orgActive = billing.data?.org_active ?? false;

  return (
    <div className="space-y-6">
      <PageHeader title="Billing" description="Manage your plan, payment method, and invoices" />

      {/* ── Hero plan card ─────────────────────────────────────────────── */}
      <Card className="card-top-accent overflow-hidden">
        <CardContent className="space-y-6 pt-8">
          <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-start">
            {billing.isLoading || !plan ? (
              <div className="space-y-3">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-10 w-48" />
                <Skeleton className="h-4 w-56" />
              </div>
            ) : (
              <div>
                <p className="eyebrow flex items-center gap-1.5">
                  <Sparkles className="h-3 w-3 text-primary" /> Current plan
                </p>
                <div className="mt-1.5 flex flex-wrap items-baseline gap-3">
                  <h2 className="font-heading text-3xl font-semibold">
                    {plan.name}
                    {plan.is_custom_pricing ? "" : " Plan"}
                  </h2>
                  <Badge variant={orgActive ? "success" : "warning"}>
                    {orgActive ? "Active" : (billing.data?.subscription_status ?? "No subscription")}
                  </Badge>
                </div>
                <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
                  {plan.is_custom_pricing ? (
                    "Custom pricing"
                  ) : (
                    <span className="text-gradient font-heading text-lg font-semibold">
                      {formatPrice(effectivePriceMinor!, plan.currency)}
                      <span className="text-sm font-normal text-muted-foreground">/month</span>
                    </span>
                  )}
                  {plan.discount_price_minor != null && (
                    <span className="text-muted-foreground/70 line-through">
                      {formatPrice(plan.price_minor, plan.currency)}
                    </span>
                  )}
                  {renewsOn && (
                    <span className="flex items-center gap-1">
                      <CalendarClock className="h-3.5 w-3.5" /> renews {renewsOn}
                    </span>
                  )}
                </p>
              </div>
            )}
            <div className="flex items-center gap-2">
              <ChangePlanDialog currentPlanId={plan?.id} userName={user?.full_name} userEmail={user?.email} />
            </div>
          </div>

          <div className="space-y-2 rounded-xl border border-border/60 bg-muted/30 p-4">
            <div className="flex items-center justify-between text-sm">
              <p className="flex items-center gap-1.5 font-medium">
                <Zap className="h-3.5 w-3.5 text-warning" /> Credits used this period
              </p>
              {credits.data && (
                <p className="tabular-figure text-muted-foreground">
                  {credits.data.used.toLocaleString()} / {credits.data.allotted.toLocaleString()} min
                </p>
              )}
            </div>
            {credits.isLoading || !credits.data ? <Skeleton className="h-2 w-full" /> : <Progress value={pct} />}
            {credits.data && credits.data.overage_minutes > 0 && (
              <p className="text-xs text-warning">
                {credits.data.overage_minutes.toLocaleString()} overage minute
                {credits.data.overage_minutes === 1 ? "" : "s"} this period
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          icon={ShieldCheck}
          label="Subscription status"
          value={billing.isLoading ? undefined : orgActive ? "Active" : "Needs attention"}
          tone={orgActive ? "success" : "warning"}
        />
        <StatCard
          icon={CalendarClock}
          label="Next renewal"
          value={billing.isLoading ? undefined : (renewsOn ?? "—")}
          tone="info"
        />
        <StatCard
          icon={Zap}
          label="Minutes included"
          value={plan ? plan.credits_per_month.toLocaleString() : undefined}
          loading={billing.isLoading}
          tone="default"
        />
      </div>

      <Card>
        <CardContent className="space-y-4 pt-6">
          <p className="flex items-center gap-2 text-sm font-medium">
            <CreditCard className="h-4 w-4 text-muted-foreground" /> Payment method
          </p>
          <div
            className={cn(
              "flex items-center gap-3 rounded-lg border px-4 py-3",
              orgActive ? "border-success/30 bg-success/5" : "border-dashed border-border"
            )}
          >
            {orgActive ? <ShieldCheck className="h-4 w-4 shrink-0 text-success" /> : null}
            <p className="text-sm text-muted-foreground">
              {orgActive
                ? "Managed securely by Razorpay — your card/UPI details are never stored on our servers."
                : "No payment method on file yet — set one up via Change plan above."}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-4 pt-6">
          <p className="flex items-center gap-2 text-sm font-medium">
            <Building2 className="h-4 w-4 text-muted-foreground" /> Billing details
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Billing email</Label>
              <Input placeholder="billing@yourcompany.com" />
            </div>
            <div className="space-y-1.5">
              <Label>Company / organization name</Label>
              <Input placeholder="Acme Corp" />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label>Billing address</Label>
              <Input placeholder="Street address, city, state, ZIP" />
            </div>
            <div className="space-y-1.5">
              <Label>Tax ID / GSTIN</Label>
              <Input placeholder="Optional" />
            </div>
            <div className="space-y-1.5">
              <Label>Billing currency</Label>
              <Input value="INR" disabled />
            </div>
          </div>
          <Button variant="gradient" size="sm" onClick={() => notImplemented("Saving billing details")}>
            Save details
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-4 pt-6">
          <p className="flex items-center gap-2 text-sm font-medium">
            <Receipt className="h-4 w-4 text-muted-foreground" /> Invoice history
          </p>
          <div className="rounded-lg border border-dashed border-border px-3 py-3 text-sm text-muted-foreground">
            Razorpay emails you a receipt after every successful charge. In-app invoice history isn't built yet.
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-3 pt-6">
          <p className="flex items-center gap-2 text-sm font-medium">
            <ListChecks className="h-4 w-4 text-muted-foreground" /> What's needed to enable payments
          </p>
          <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
            <ChecklistItem done={orgActive} label="Payment method on file" />
            <ChecklistItem done={false} label="Billing email confirmed" />
            <ChecklistItem done={false} label="Billing address" />
            <ChecklistItem done label="Organization verified" />
            <ChecklistItem done={false} label="Tax ID (if applicable)" />
          </div>
          <p className="border-t border-border/60 pt-3 text-xs text-muted-foreground">
            These are the details typically required before charges can be processed. Billing email/address/Tax ID
            aren't collected yet — this section is a UI preview only for those.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function ChecklistItem({ done, label }: { done: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      {done ? (
        <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
      ) : (
        <Circle className="h-4 w-4 shrink-0 text-muted-foreground" />
      )}
      <span className={done ? "" : "text-muted-foreground"}>{label}</span>
    </div>
  );
}

function ChangePlanDialog({
  currentPlanId,
  userName,
  userEmail,
}: {
  currentPlanId?: string;
  userName?: string;
  userEmail?: string;
}) {
  const [open, setOpen] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState<PublicPlan | null>(null);
  const [paying, setPaying] = useState(false);
  const checkout = useCheckout();
  const verifyPayment = useVerifyPayment();

  async function confirm() {
    if (!selectedPlan) return;
    setPaying(true);
    try {
      const result = await checkout.mutateAsync(selectedPlan.id);
      if (result.action === "new" && result.subscription_id && result.razorpay_key_id) {
        await openRazorpayCheckout({
          key: result.razorpay_key_id,
          subscription_id: result.subscription_id,
          name: "QuickHowl",
          description: `${result.plan_name} plan`,
          prefill: { name: userName, email: userEmail },
          theme: { color: "#2563eb" },
          handler: async (response) => {
            try {
              await verifyPayment.mutateAsync(response);
            } finally {
              toast.success("Payment received — your plan is updating");
              setOpen(false);
            }
          },
          modal: { ondismiss: () => setPaying(false) },
        });
      } else {
        toast.success("Plan updated");
        setOpen(false);
      }
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't start checkout"));
    } finally {
      setPaying(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="gradient" size="sm">
          Change plan
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Choose a plan</DialogTitle>
        </DialogHeader>
        <PlanPicker selectedPlanId={selectedPlan?.id ?? null} onSelect={setSelectedPlan} excludePlanId={currentPlanId} />
        <DialogFooter>
          <Button variant="gradient" onClick={confirm} disabled={!selectedPlan || paying}>
            {paying && <Loader2 className="h-4 w-4 animate-spin" />}
            Continue to payment
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
