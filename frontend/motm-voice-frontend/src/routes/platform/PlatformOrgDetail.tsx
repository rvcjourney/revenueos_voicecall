import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, ExternalLink, Loader2, Receipt, RotateCcw, ShieldOff, ShieldCheck, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { StatCard } from "@/components/shared/StatCard";
import { ConfirmDialog } from "@/components/platform/ConfirmDialog";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { PlatformCallsChart, PlatformCreditsChart } from "@/components/charts/PlatformUsageCharts";
import {
  useAdjustPlatformOrgCredits,
  useDeletePlatformOrg,
  usePlatformOrg,
  usePlatformOrgInvoices,
  usePlatformOrgUsageAnalytics,
  usePlatformPlans,
  useResetPlatformOrgCredits,
  useUpdatePlatformOrg,
} from "@/lib/platformHooks";
import { platformApiErrorMessage, platformOrgsApi } from "@/lib/platformApi";
import { formatDate } from "@/lib/utils";

function formatPrice(priceMinor: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(
    priceMinor / 100
  );
}

function triggerPdfDownload(bytes: BlobPart, filename: string) {
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function PlatformOrgDetail() {
  const { id } = useParams<{ id: string }>();
  const org = usePlatformOrg(id);

  if (org.isError) {
    return <ErrorBanner error={org.error} onRetry={() => org.refetch()} />;
  }

  return (
    <div className="space-y-6">
      <Link to="/ops/organizations" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to organizations
      </Link>

      {org.isLoading || !org.data ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <>
          <PageHeader
            title={org.data.name}
            description={org.data.slug}
            actions={
              <>
                <Badge variant={org.data.is_active ? "success" : "muted"}>
                  {org.data.is_active ? "Active" : "Suspended"}
                </Badge>
                <Badge variant="secondary" className="capitalize">
                  {org.data.plan_name}
                </Badge>
              </>
            }
          />

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Users" value={org.data.users_count} />
            <StatCard label="Subscription" value={org.data.subscription_status} />
            <StatCard
              label="Next renewal"
              value={org.data.subscription_current_period_end ? formatDate(org.data.subscription_current_period_end) : "—"}
            />
            <StatCard
              label="Credits used"
              value={`${org.data.credits_used_this_period.toLocaleString()} / ${org.data.credits_per_month.toLocaleString()}`}
            />
            <StatCard
              label="Plan price"
              value={
                org.data.plan_price_minor != null && org.data.plan_currency
                  ? formatPrice(org.data.plan_discount_price_minor ?? org.data.plan_price_minor, org.data.plan_currency)
                  : "—"
              }
            />
          </div>

          <SuspendCard id={org.data.id} isActive={org.data.is_active} orgName={org.data.name} />
          <SettingsCard
            id={org.data.id}
            planId={org.data.plan_name}
            monthlyCallQuota={org.data.monthly_call_quota}
            elevenlabsEnabled={org.data.elevenlabs_enabled}
          />
          <CreditsCard id={org.data.id} />
          <PaymentHistoryCard id={org.data.id} />
          <UsageCard id={org.data.id} />
          <DeleteCard id={org.data.id} orgName={org.data.name} hasPlan={!!org.data.plan_name} />
        </>
      )}
    </div>
  );
}

function DeleteCard({ id, orgName, hasPlan }: { id: string; orgName: string; hasPlan: boolean }) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const navigate = useNavigate();
  const del = useDeletePlatformOrg();

  async function handleConfirm() {
    try {
      await del.mutateAsync(id);
      toast.success("Organization deleted");
      navigate("/ops/organizations");
    } catch (err) {
      toast.error(platformApiErrorMessage(err, "Couldn't delete organization"));
    }
  }

  return (
    <Card className="border-destructive/30">
      <CardHeader>
        <CardTitle className="text-destructive">Danger zone</CardTitle>
        <CardDescription>
          {hasPlan
            ? "This org has an active subscription — cancel it before it can be deleted, or suspend the org instead for a reversible block."
            : "This org has no active plan. Deleting removes it from every list here — its data is kept for audit, not erased, but it cannot be recovered through this console."}
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        <Button variant="destructive" onClick={() => setConfirmOpen(true)} disabled={hasPlan}>
          <Trash2 className="h-3.5 w-3.5" /> Delete organization
        </Button>
      </CardContent>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Delete ${orgName}?`}
        description="This permanently removes the organization from every SuperAdmin listing. This cannot be undone from here."
        confirmLabel="Delete"
        variant="destructive"
        loading={del.isPending}
        onConfirm={handleConfirm}
      />
    </Card>
  );
}

function SuspendCard({ id, isActive, orgName }: { id: string; isActive: boolean; orgName: string }) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const update = useUpdatePlatformOrg();

  async function handleConfirm() {
    try {
      await update.mutateAsync({ id, data: { is_active: !isActive } });
      toast.success(isActive ? "Organization suspended" : "Organization reactivated");
      setConfirmOpen(false);
    } catch (err) {
      toast.error(platformApiErrorMessage(err, "Couldn't update organization"));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Account status</CardTitle>
        <CardDescription>
          {isActive
            ? "This organization can log in and place calls."
            : "This organization is suspended — its users cannot log in or place calls."}
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        <Button variant={isActive ? "destructive" : "gradient"} onClick={() => setConfirmOpen(true)}>
          {isActive ? <ShieldOff className="h-3.5 w-3.5" /> : <ShieldCheck className="h-3.5 w-3.5" />}
          {isActive ? "Suspend organization" : "Reactivate organization"}
        </Button>
      </CardContent>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={isActive ? "Suspend this organization?" : "Reactivate this organization?"}
        description={
          isActive
            ? `${orgName} is a paying customer. Suspending blocks every user in this org from logging in or placing calls, immediately.`
            : `${orgName} will regain full access immediately.`
        }
        confirmLabel={isActive ? "Suspend" : "Reactivate"}
        variant={isActive ? "destructive" : "default"}
        loading={update.isPending}
        onConfirm={handleConfirm}
      />
    </Card>
  );
}

function SettingsCard({
  id,
  planId,
  monthlyCallQuota,
  elevenlabsEnabled,
}: {
  id: string;
  planId: string;
  monthlyCallQuota: number;
  elevenlabsEnabled: boolean;
}) {
  const plans = usePlatformPlans();
  const update = useUpdatePlatformOrg();

  // planId from the org payload is the plan's display name, not its id (the
  // detail/list endpoints only return plan_name) — default the selector to the
  // plan whose name matches, and fall back to no selection if it can't be found.
  const [selectedPlanId, setSelectedPlanId] = useState<string>("");
  const [quota, setQuota] = useState(String(monthlyCallQuota));
  const [elevenlabs, setElevenlabs] = useState(elevenlabsEnabled);

  useEffect(() => {
    if (!plans.data) return;
    const match = plans.data.find((p) => p.name === planId);
    if (match) setSelectedPlanId(match.id);
  }, [plans.data, planId]);

  useEffect(() => {
    setQuota(String(monthlyCallQuota));
    setElevenlabs(elevenlabsEnabled);
  }, [monthlyCallQuota, elevenlabsEnabled]);

  async function handleSave() {
    const parsedQuota = Number(quota);
    if (!Number.isFinite(parsedQuota) || parsedQuota < 0) {
      toast.error("Monthly call quota must be a non-negative number");
      return;
    }
    try {
      await update.mutateAsync({
        id,
        data: {
          plan_id: selectedPlanId || undefined,
          monthly_call_quota: parsedQuota,
          elevenlabs_enabled: elevenlabs,
        },
      });
      toast.success("Organization updated");
    } catch (err) {
      toast.error(platformApiErrorMessage(err, "Couldn't update organization"));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Plan & limits</CardTitle>
        <CardDescription>
          Changing plan reprorates credits mid-period — the numbers above refresh after saving.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Plan</Label>
            <Select value={selectedPlanId} onValueChange={setSelectedPlanId}>
              <SelectTrigger>
                <SelectValue placeholder="Select a plan" />
              </SelectTrigger>
              <SelectContent>
                {plans.data?.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Monthly call quota</Label>
            <Input type="number" min={0} value={quota} onChange={(e) => setQuota(e.target.value)} />
          </div>
        </div>
        <div className="flex items-center justify-between rounded-lg border border-border p-3">
          <div>
            <p className="text-sm font-medium">ElevenLabs voices</p>
            <p className="text-xs text-muted-foreground">Feature flag for this organization.</p>
          </div>
          <Switch checked={elevenlabs} onCheckedChange={setElevenlabs} />
        </div>
        <Button variant="gradient" onClick={handleSave} disabled={update.isPending}>
          {update.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          Save changes
        </Button>
      </CardContent>
    </Card>
  );
}

function CreditsCard({ id }: { id: string }) {
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("");
  const [adjustConfirmOpen, setAdjustConfirmOpen] = useState(false);
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);

  const adjust = useAdjustPlatformOrgCredits();
  const reset = useResetPlatformOrgCredits();

  const parsedDelta = Number(delta);
  const deltaIsValid = delta.trim() !== "" && Number.isFinite(parsedDelta) && parsedDelta !== 0;
  const canSubmitAdjust = deltaIsValid && reason.trim().length > 0;

  async function handleAdjustConfirm() {
    try {
      await adjust.mutateAsync({ id, data: { delta: parsedDelta, reason: reason.trim() } });
      toast.success("Credits adjusted");
      setDelta("");
      setReason("");
      setAdjustConfirmOpen(false);
    } catch (err) {
      toast.error(platformApiErrorMessage(err, "Couldn't adjust credits"));
    }
  }

  async function handleResetConfirm() {
    try {
      await reset.mutateAsync(id);
      toast.success("Billing period reset");
      setResetConfirmOpen(false);
    } catch (err) {
      toast.error(platformApiErrorMessage(err, "Couldn't reset billing period"));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Credits</CardTitle>
        <CardDescription>
          Positive delta consumes credits (e.g. correcting for calls billed outside the normal flow); negative delta
          grants credits (goodwill/bonus). Result clamps at 0. Every adjustment is audited with the reason below.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5 pt-0">
        <div className="grid gap-4 sm:grid-cols-[160px_1fr]">
          <div className="space-y-1.5">
            <Label>Delta</Label>
            <Input type="number" placeholder="e.g. -50" value={delta} onChange={(e) => setDelta(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Reason (required)</Label>
            <Textarea
              placeholder="Why is this adjustment being made?"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
        </div>
        <Button variant="gradient" onClick={() => setAdjustConfirmOpen(true)} disabled={!canSubmitAdjust}>
          Adjust credits
        </Button>

        <div className="flex items-center justify-between border-t border-border pt-4">
          <div>
            <p className="text-sm font-medium">Reset billing period now</p>
            <p className="text-xs text-muted-foreground">Zeroes usage and restarts the period immediately.</p>
          </div>
          <Button variant="destructive" size="sm" onClick={() => setResetConfirmOpen(true)}>
            <RotateCcw className="h-3.5 w-3.5" /> Reset
          </Button>
        </div>
      </CardContent>

      <ConfirmDialog
        open={adjustConfirmOpen}
        onOpenChange={setAdjustConfirmOpen}
        title="Confirm credit adjustment"
        description={
          deltaIsValid
            ? `This will ${parsedDelta > 0 ? "consume" : "grant"} ${Math.abs(parsedDelta).toLocaleString()} credits. Reason: "${reason.trim()}"`
            : "Enter a delta and reason first."
        }
        confirmLabel="Apply adjustment"
        loading={adjust.isPending}
        onConfirm={handleAdjustConfirm}
      />

      <ConfirmDialog
        open={resetConfirmOpen}
        onOpenChange={setResetConfirmOpen}
        title="Reset billing period now?"
        description="This immediately zeroes this organization's usage and restarts its billing period. This cannot be undone."
        confirmLabel="Reset now"
        variant="destructive"
        loading={reset.isPending}
        onConfirm={handleResetConfirm}
      />
    </Card>
  );
}

function PaymentHistoryCard({ id }: { id: string }) {
  const invoices = usePlatformOrgInvoices(id);

  async function download(invoiceId: string, invoiceNumber: string) {
    try {
      const resp = await platformOrgsApi.downloadInvoice(id, invoiceId);
      triggerPdfDownload(resp.data, `${invoiceNumber}.pdf`);
    } catch (err) {
      toast.error(platformApiErrorMessage(err, "Couldn't download invoice"));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Receipt className="h-4 w-4 text-muted-foreground" /> Payment history
        </CardTitle>
        <CardDescription>QuickHowl's own GST tax invoices generated for this client's charges.</CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        {invoices.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : !invoices.data || invoices.data.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border px-3 py-3 text-sm text-muted-foreground">
            No invoices yet for this client.
          </div>
        ) : (
          <div className="divide-y divide-border/60 overflow-hidden rounded-lg border border-border">
            {invoices.data.map((inv) => (
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
                  <span className="text-muted-foreground">{inv.plan_name}</span>
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

function UsageCard({ id }: { id: string }) {
  const usage = usePlatformOrgUsageAnalytics(id);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Usage (last 30 days)</CardTitle>
        <CardDescription>Calls and credits used by this organization, day by day.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6 pt-0">
        {usage.isError ? (
          <ErrorBanner error={usage.error} onRetry={() => usage.refetch()} />
        ) : usage.isLoading || !usage.data ? (
          <Skeleton className="h-60 w-full" />
        ) : (
          <>
            <div>
              <p className="mb-2 text-sm font-medium text-muted-foreground">Calls per day</p>
              <PlatformCallsChart data={usage.data.series} height={200} />
            </div>
            <div>
              <p className="mb-2 text-sm font-medium text-muted-foreground">Credits used per day</p>
              <PlatformCreditsChart data={usage.data.series} height={200} />
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
