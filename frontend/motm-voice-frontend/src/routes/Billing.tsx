import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Building2,
  CalendarClock,
  CheckCircle2,
  Circle,
  CreditCard,
  ExternalLink,
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
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { PlanPicker } from "@/components/billing/PlanPicker";
import { BillingAddressForm } from "@/components/billing/BillingAddressForm";
import { CREDIT_WARNING_THRESHOLD_PCT } from "@/components/dashboard/QuotaConcurrencyCard";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { apiErrorMessage, billingApi } from "@/lib/api";
import {
  useBillingAddress,
  useBillingCurrent,
  useCheckout,
  useCreditUsage,
  useTaxInvoices,
  useVerifyPayment,
} from "@/lib/hooks";
import { openRazorpayCheckout } from "@/lib/razorpayCheckout";
import type { PublicPlan } from "@/lib/types";

function triggerPdfDownload(bytes: BlobPart, filename: string) {
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

// The GST tax invoice for a payment isn't generated synchronously in the
// verify-payment response -- it happens once Razorpay's subscription.charged
// webhook lands (app/api/webhooks.py), usually within a few seconds but not
// guaranteed instant. Polls briefly and downloads it the moment it appears;
// gives up quietly after ~16s (it's still there in Tax invoices whenever it
// does land -- this is a nice-to-have, not something worth blocking on).
async function pollAndAutoDownloadInvoice(countBefore: number) {
  for (let i = 0; i < 8; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    try {
      const res = await billingApi.taxInvoices();
      const invoices = res.data.invoices;
      if (invoices.length > countBefore) {
        const latest = invoices[0];
        const pdfResp = await billingApi.downloadTaxInvoice(latest.id);
        triggerPdfDownload(pdfResp.data, `${latest.invoice_number}.pdf`);
        return;
      }
    } catch {
      // keep polling — the invoice is still browsable later in Tax invoices either way
    }
  }
}

function formatPrice(priceMinor: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(
    priceMinor / 100
  );
}

export default function Billing() {
  const billing = useBillingCurrent();

  // /billing/current 404s for any org with no Subscription row yet (never
  // finished checkout, e.g. skipped it at signup) -- that's not a loading
  // state, it never resolves, so show the plan picker directly instead of
  // leaving the page stuck on skeletons forever.
  if (billing.isError) {
    return <NoPlanBilling />;
  }

  return <ActivePlanBilling billing={billing} />;
}

function ActivePlanBilling({ billing }: { billing: ReturnType<typeof useBillingCurrent> }) {
  const { user } = useAuth();
  const credits = useCreditUsage();
  const billingAddress = useBillingAddress();
  const pct = credits.data ? Math.min((credits.data.used / Math.max(credits.data.allotted, 1)) * 100, 100) : 0;
  const creditsNear = pct >= CREDIT_WARNING_THRESHOLD_PCT;

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
            {credits.data && credits.data.overage_minutes === 0 && creditsNear && (
              <p className="text-xs text-warning">Approaching credit limit — {Math.round(pct)}% used. Add credits before you run out.</p>
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

      <BillingDetailsCard />

      <TaxInvoiceHistoryCard />

      <Card>
        <CardContent className="space-y-3 pt-6">
          <p className="flex items-center gap-2 text-sm font-medium">
            <ListChecks className="h-4 w-4 text-muted-foreground" /> What's needed to enable payments
          </p>
          <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
            <ChecklistItem done={orgActive} label="Payment method on file" />
            <ChecklistItem done={false} label="Billing email confirmed" />
            <ChecklistItem done={!!billingAddress.data?.state} label="Billing address" />
            <ChecklistItem done label="Organization verified" />
            <ChecklistItem done={!!billingAddress.data?.gstin} label="Tax ID (if applicable)" />
          </div>
          <p className="border-t border-border/60 pt-3 text-xs text-muted-foreground">
            These are the details typically required before charges can be processed. Billing email confirmation
            isn't tracked yet — everything else here reflects your real account state.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function BillingDetailsCard() {
  const billingAddress = useBillingAddress();

  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <p className="flex items-center gap-2 text-sm font-medium">
          <Building2 className="h-4 w-4 text-muted-foreground" /> Billing details
        </p>
        {billingAddress.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <BillingAddressForm onSaved={() => billingAddress.refetch()} initial={billingAddress.data} />
        )}
      </CardContent>
    </Card>
  );
}

function TaxInvoiceHistoryCard() {
  const taxInvoices = useTaxInvoices();

  async function download(id: string, invoiceNumber: string) {
    try {
      const resp = await billingApi.downloadTaxInvoice(id);
      triggerPdfDownload(resp.data, `${invoiceNumber}.pdf`);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't download invoice"));
    }
  }

  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <p className="flex items-center gap-2 text-sm font-medium">
          <Receipt className="h-4 w-4 text-muted-foreground" /> Tax invoices
        </p>

        {taxInvoices.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : !taxInvoices.data || taxInvoices.data.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border px-3 py-3 text-sm text-muted-foreground">
            No tax invoices yet — one appears here after your first successful charge.
          </div>
        ) : (
          <div className="divide-y divide-border/60 overflow-hidden rounded-lg border border-border">
            {taxInvoices.data.map((inv) => (
              <div key={inv.id} className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm">
                <div className="flex items-center gap-3">
                  <span className="text-muted-foreground">
                    {new Date(inv.issued_at).toLocaleDateString(undefined, {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">{inv.invoice_number}</span>
                  <span className="font-medium">{formatPrice(inv.total_minor, inv.currency)}</span>
                </div>
                <button
                  onClick={() => download(inv.id, inv.invoice_number)}
                  className="flex items-center gap-1 text-primary hover:underline"
                >
                  Download <ExternalLink className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function NoPlanBilling() {
  const { user } = useAuth();
  const checkout = useCheckout();
  const verifyPayment = useVerifyPayment();
  const qc = useQueryClient();
  const billingAddress = useBillingAddress();
  const [selectedPlan, setSelectedPlan] = useState<PublicPlan | null>(null);
  const [paying, setPaying] = useState(false);

  async function startPayment() {
    if (!selectedPlan) {
      toast.error("Pick a plan first");
      return;
    }
    setPaying(true);
    try {
      const invoiceCountBefore = (await billingApi.taxInvoices()).data.invoices.length;
      const result = await checkout.mutateAsync(selectedPlan.id);
      if (result.action === "new" && result.subscription_id && result.razorpay_key_id) {
        // Don't refresh billing-current yet -- a real but UNPAID Subscription
        // row now exists just so Razorpay Checkout has something to
        // authorize. Only the payment handler below (via useVerifyPayment)
        // should make this page start showing it as the org's plan.
        await openRazorpayCheckout({
          key: result.razorpay_key_id,
          subscription_id: result.subscription_id,
          name: "QuickHowl",
          description: `${result.plan_name} plan`,
          prefill: { name: user?.full_name, email: user?.email },
          theme: { color: "#2563eb" },
          handler: async (response) => {
            try {
              await verifyPayment.mutateAsync(response);
            } finally {
              toast.success("Payment received — activating your account...");
              void pollAndAutoDownloadInvoice(invoiceCountBefore);
            }
          },
          modal: { ondismiss: () => setPaying(false) },
        });
      } else {
        // action:"change" completes synchronously server-side, so this one
        // really is safe (and necessary) to reflect immediately. The charge
        // itself already happened too (schedule_change_at:"now") -- the tax
        // invoice just may not have landed from the webhook yet.
        await qc.invalidateQueries({ queryKey: ["billing-current"] });
        toast.success("Plan updated");
        void pollAndAutoDownloadInvoice(invoiceCountBefore);
      }
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't start checkout"));
      setPaying(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Billing" description="Manage your plan, payment method, and invoices" />
      <Card className="card-top-accent overflow-hidden">
        <CardContent className="space-y-6 pt-8">
          <div>
            <p className="eyebrow flex items-center gap-1.5">
              <Sparkles className="h-3 w-3 text-primary" /> Get started
            </p>
            <h2 className="mt-1.5 font-heading text-2xl font-semibold sm:text-3xl">
              Choose a plan to activate your account
            </h2>
            <p className="mt-2 max-w-xl text-sm text-muted-foreground">
              You don't have an active subscription yet, so calls can't go out until you pick a plan and complete
              payment. Your account and settings are otherwise all set up.
            </p>
          </div>
          <PlanPicker selectedPlanId={selectedPlan?.id ?? null} onSelect={setSelectedPlan} />
          {!billingAddress.isLoading && !billingAddress.data?.state ? (
            <BillingAddressForm onSaved={() => billingAddress.refetch()} />
          ) : (
            <Button
              variant="gradient"
              size="lg"
              className="w-full sm:w-auto"
              onClick={startPayment}
              disabled={!selectedPlan || paying}
            >
              {paying && <Loader2 className="h-4 w-4 animate-spin" />}
              Continue to payment
            </Button>
          )}
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
  const qc = useQueryClient();
  const billingAddress = useBillingAddress();

  async function confirm() {
    if (!selectedPlan) return;
    setPaying(true);
    try {
      const invoiceCountBefore = (await billingApi.taxInvoices()).data.invoices.length;
      const result = await checkout.mutateAsync(selectedPlan.id);
      if (result.action === "new" && result.subscription_id && result.razorpay_key_id) {
        // Don't refresh billing-current yet -- see NoPlanBilling's comment;
        // useVerifyPayment below is what should reflect the new plan.
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
              void pollAndAutoDownloadInvoice(invoiceCountBefore);
            }
          },
          modal: { ondismiss: () => setPaying(false) },
        });
      } else {
        // action:"change" completes synchronously server-side — safe to
        // reflect immediately. The charge already happened too
        // (schedule_change_at:"now") -- the tax invoice just may not have
        // landed from the webhook yet.
        await qc.invalidateQueries({ queryKey: ["billing-current"] });
        toast.success("Plan updated");
        setOpen(false);
        void pollAndAutoDownloadInvoice(invoiceCountBefore);
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
        {!billingAddress.isLoading && !billingAddress.data?.state && (
          <BillingAddressForm onSaved={() => billingAddress.refetch()} />
        )}
        <DialogFooter>
          <Button
            variant="gradient"
            onClick={confirm}
            disabled={!selectedPlan || paying || !billingAddress.data?.state}
          >
            {paying && <Loader2 className="h-4 w-4 animate-spin" />}
            Continue to payment
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
