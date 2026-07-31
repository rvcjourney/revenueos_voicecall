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
  Plus,
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
import { PageHeader } from "@/components/shared/PageHeader";
import { useCreditUsage } from "@/lib/hooks";

const CURRENT_PLAN = {
  name: "Starter Plan",
  price: "$49",
  interval: "month",
  renewsOn: "31 Aug 2026",
};

function notImplemented(action: string) {
  toast.info(`${action} isn't connected yet — this is a UI preview only.`);
}

export default function Billing() {
  const credits = useCreditUsage();
  const pct = credits.data ? Math.min((credits.data.used / Math.max(credits.data.allotted, 1)) * 100, 100) : 0;

  return (
    <div className="space-y-6">
      <PageHeader title="Billing" description="Manage your plan, payment method, and invoices" />

      <Card>
        <CardContent className="space-y-5 pt-6">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
            <div>
              <p className="font-heading text-xl font-semibold">{CURRENT_PLAN.name}</p>
              <p className="text-sm text-muted-foreground">
                {CURRENT_PLAN.price}/{CURRENT_PLAN.interval} · renews {CURRENT_PLAN.renewsOn}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="success">
                <Check className="h-3 w-3" /> Active
              </Badge>
              <Button variant="outline" size="sm" onClick={() => notImplemented("Changing plans")}>
                Change plan
              </Button>
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
          <div className="flex items-center justify-between gap-3">
            <p className="flex items-center gap-2 text-sm font-medium">
              <CreditCard className="h-4 w-4 text-muted-foreground" /> Payment method
            </p>
            <AddPaymentMethodDialog />
          </div>
          <div className="flex items-center justify-between rounded-lg border border-dashed border-border px-3 py-3">
            <p className="text-sm text-muted-foreground">No payment method on file</p>
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
            No invoices yet — they'll appear here after your first billing cycle.
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-3 pt-6">
          <p className="flex items-center gap-2 text-sm font-medium">
            <ListChecks className="h-4 w-4 text-muted-foreground" /> What's needed to enable payments
          </p>
          <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
            <ChecklistItem done={false} label="Payment method on file" />
            <ChecklistItem done={false} label="Billing email confirmed" />
            <ChecklistItem done={false} label="Billing address" />
            <ChecklistItem done label="Organization verified" />
            <ChecklistItem done={false} label="Tax ID (if applicable)" />
          </div>
          <p className="border-t border-border/60 pt-3 text-xs text-muted-foreground">
            These are the details typically required before charges can be processed. Payment processing itself isn't
            connected yet — this page is a UI preview only.
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

function AddPaymentMethodDialog() {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  function handleSave() {
    setSaving(true);
    setTimeout(() => {
      setSaving(false);
      setOpen(false);
      notImplemented("Adding a payment method");
    }, 400);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Plus className="h-3.5 w-3.5" /> Add payment method
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add payment method</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Cardholder name</Label>
            <Input placeholder="Full name on card" />
          </div>
          <div className="space-y-1.5">
            <Label>Card number</Label>
            <Input placeholder="1234 1234 1234 1234" inputMode="numeric" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Expiry</Label>
              <Input placeholder="MM/YY" />
            </div>
            <div className="space-y-1.5">
              <Label>CVV</Label>
              <Input placeholder="123" inputMode="numeric" />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="gradient" onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            Save card
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
