import { Link, useLocation } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { useBillingCurrent, useBillingEnabled } from "@/lib/hooks";

// Shown across the authed app whenever the org has no active Razorpay
// subscription yet (brand-new self-serve org that skipped payment, or a
// subscription that lapsed/was halted) — org.is_active is enforced
// server-side (campaign launch, etc.), this is just the visible nudge.
export function SubscriptionBanner() {
  const billingEnabled = useBillingEnabled();
  const billing = useBillingCurrent(billingEnabled);
  const location = useLocation();

  const needsAttention = billing.isError || (billing.data && !billing.data.org_active);
  if (!billingEnabled || !needsAttention || location.pathname === "/billing") return null;

  return (
    <Link
      to="/billing"
      className="mb-4 flex items-center gap-2 rounded-xl border border-warning/40 bg-warning/10 px-4 py-2.5 text-sm text-warning hover:bg-warning/15"
    >
      <AlertTriangle className="h-4 w-4 shrink-0" />
      Your subscription isn't active yet — complete payment to start making calls.
      <span className="ml-auto font-medium underline">Go to Billing</span>
    </Link>
  );
}
