import { useState } from "react";
import { toast } from "sonner";
import {
  Building2,
  Check,
  CheckCircle2,
  Circle,
  CreditCard,
  ListChecks,
  Loader2,
  Receipt,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/platform/ConfirmDialog";
import { PageHeader } from "@/components/shared/PageHeader";
import { PlanPicker } from "@/components/billing/PlanPicker";
import { useAuth } from "@/lib/auth";
import { apiErrorMessage } from "@/lib/api";
import { useBillingCurrent, useCancelSubscription, useCheckout, useCreditUsage, useVerifyPayment } from "@/lib/hooks";
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
  const isActiveSubscription = billing.data?.subscription_status === "active";

  return (
    <div className="space-y-6">
      <PageHeader title="Billing" description="Manage your plan, payment method, and invoices" />

      <Card>
        <CardContent className="space-y-5 pt-6">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
            {billing.isLoading || !plan ? (
              <div className="space-y-2">
                <Skeleton className="h-6 w-40" />
                <Skeleton className="h-4 w-56" />
              </div>
            ) : (
              <div>
                <p className="font-heading text-xl font-semibold">
                  {plan.name}
                  {plan.is_custom_pricing ? "" : " Plan"}
                </p>
                <p className="text-sm text-muted-foreground">
                  {plan.is_custom_pricing ? (
                    "Custom pricing"
                  ) : (
                    <>
                      {formatPrice(effectivePriceMinor!, plan.currency)}/month
                      {plan.discount_price_minor != null && (
                        <span className="ml-1.5 text-muted-foreground/70 line-through">
                          {formatPrice(plan.price_minor, plan.currency)}
                        </span>
                      )}
                    </>
                  )}
                  {renewsOn && <> · renews {renewsOn}</>}
                </p>
              </div>
            )}
            <div className="flex items-center gap-2">
              <Badge variant={isActiveSubscription ? "success" : "warning"}>
                <Check className="h-3 w-3" /> {billing.data?.subscription_status ?? "No subscription"}
              </Badge>
              <ChangePlanDialog currentPlanId={plan?.id} userName={user?.full_name} userEmail={user?.email} />
              {isActiveSubscription && <CancelSubscriptionButton />}
            </div>
          </div>

          <div className="space-y-2 border-t border-border/60 pt-4">
            <div className="flex items-center justify-between text-sm">
              <p className="font-medium">Credits used this period</p>
              {credits.data && (
                <p className="text-muted-foreground">
                  {credits.data.used.toLocaleString()} / {credits.data.allotted.toLocaleString()}
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

      <Card>
        <CardContent className="space-y-4 pt-6">
          <p className="flex items-center gap-2 text-sm font-medium">
            <CreditCard className="h-4 w-4 text-muted-foreground" /> Payment method
          </p>
          <div className="flex items-center justify-between rounded-lg border border-dashed border-border px-3 py-3">
            <p className="text-sm text-muted-foreground">
              {isActiveSubscription
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
            <ChecklistItem done={isActiveSubscription} label="Payment method on file" />
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
          name: "Talkryn",
          description: `${result.plan_name} plan`,
          prefill: { name: userName, email: userEmail },
          theme: { color: "#6366f1" },
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
        <Button variant="outline" size="sm">
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

function CancelSubscriptionButton() {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const cancel = useCancelSubscription();

  async function handleConfirm() {
    try {
      await cancel.mutateAsync();
      toast.success("Subscription will end at the close of the current billing cycle");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't cancel subscription"));
    } finally {
      setConfirmOpen(false);
    }
  }

  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => setConfirmOpen(true)}>
        Cancel subscription
      </Button>
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Cancel your subscription?"
        description="You'll keep access until the end of the current billing cycle, then your organization will be suspended."
        confirmLabel="Cancel subscription"
        variant="destructive"
        loading={cancel.isPending}
        onConfirm={handleConfirm}
      />
    </>
  );
}
