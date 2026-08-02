import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { EmptyState } from "@/components/shared/EmptyState";
import { ConfirmDialog } from "@/components/platform/ConfirmDialog";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useCreatePlatformPlan, usePlatformPlans, useUpdatePlatformPlan } from "@/lib/platformHooks";
import { platformApiErrorMessage } from "@/lib/platformApi";
import type { PlatformPlan, PlatformPlanCreate } from "@/lib/platformTypes";

function formatPrice(priceMinor: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(priceMinor / 100);
}

interface PlanFormState {
  name: string;
  price_minor: string;
  currency: string;
  monthly_call_quota: string;
  max_concurrent_calls: string;
  credits_per_month: string;
  credit_price_cents: string;
  features: { key: string; value: string }[];
  is_active: boolean;
  discount_price_minor: string;
  is_custom_pricing: boolean;
  is_highlighted: boolean;
  marketing_bullets: string[];
}

function emptyForm(): PlanFormState {
  return {
    name: "",
    price_minor: "",
    currency: "INR",
    monthly_call_quota: "",
    max_concurrent_calls: "",
    credits_per_month: "500",
    credit_price_cents: "10",
    features: [],
    is_active: true,
    discount_price_minor: "",
    is_custom_pricing: false,
    is_highlighted: false,
    marketing_bullets: [],
  };
}

function formFromPlan(plan: PlatformPlan): PlanFormState {
  return {
    name: plan.name,
    price_minor: String(plan.price_minor),
    currency: plan.currency,
    monthly_call_quota: String(plan.monthly_call_quota),
    max_concurrent_calls: String(plan.max_concurrent_calls),
    credits_per_month: String(plan.credits_per_month),
    credit_price_cents: String(plan.credit_price_cents),
    features: Object.entries(plan.features ?? {}).map(([key, value]) => ({ key, value: String(value) })),
    is_active: plan.is_active,
    discount_price_minor: plan.discount_price_minor != null ? String(plan.discount_price_minor) : "",
    is_custom_pricing: plan.is_custom_pricing,
    is_highlighted: plan.is_highlighted,
    marketing_bullets: plan.marketing_bullets ?? [],
  };
}

function toPayload(form: PlanFormState): PlatformPlanCreate {
  const features: Record<string, string> = {};
  for (const row of form.features) {
    if (row.key.trim()) features[row.key.trim()] = row.value;
  }
  return {
    name: form.name.trim(),
    price_minor: Number(form.price_minor) || 0,
    currency: form.currency.trim() || "INR",
    monthly_call_quota: Number(form.monthly_call_quota) || 0,
    max_concurrent_calls: Number(form.max_concurrent_calls) || 0,
    credits_per_month: Number(form.credits_per_month) || 0,
    credit_price_cents: Number(form.credit_price_cents) || 0,
    features,
    is_active: form.is_active,
    discount_price_minor: form.discount_price_minor.trim() === "" ? null : Number(form.discount_price_minor),
    is_custom_pricing: form.is_custom_pricing,
    is_highlighted: form.is_highlighted,
    marketing_bullets: form.marketing_bullets.filter((b) => b.trim() !== ""),
  };
}

export default function PlatformPlans() {
  const plans = usePlatformPlans();
  const [createOpen, setCreateOpen] = useState(false);
  const [editingPlan, setEditingPlan] = useState<PlatformPlan | null>(null);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Plans"
        description="Billing plans available to organizations."
        actions={
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button variant="gradient" size="sm">
                <Plus className="h-3.5 w-3.5" /> New plan
              </Button>
            </DialogTrigger>
            <PlanFormDialogContent onDone={() => setCreateOpen(false)} />
          </Dialog>
        }
      />

      {plans.isError ? (
        <ErrorBanner error={plans.error} onRetry={() => plans.refetch()} />
      ) : plans.isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : !plans.data || plans.data.length === 0 ? (
        <EmptyState title="No plans yet" description="Create the first billing plan to get started." />
      ) : (
        <Card className="overflow-hidden py-0">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="pl-5">Plan</TableHead>
                <TableHead>Price</TableHead>
                <TableHead>Call quota</TableHead>
                <TableHead>Concurrency</TableHead>
                <TableHead>Credits</TableHead>
                <TableHead>Features</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="pr-5 text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {plans.data.map((plan) => (
                <TableRow key={plan.id}>
                  <TableCell className="pl-5 text-sm font-medium">
                    <div className="flex items-center gap-1.5">
                      {plan.name}
                      {plan.is_highlighted && (
                        <Badge variant="info" className="text-[11px]">Highlighted</Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">
                    {plan.is_custom_pricing ? (
                      <span className="text-muted-foreground">Custom</span>
                    ) : plan.discount_price_minor != null ? (
                      <span className="flex items-center gap-1.5">
                        <span className="text-muted-foreground line-through">
                          {formatPrice(plan.price_minor, plan.currency)}
                        </span>
                        {formatPrice(plan.discount_price_minor, plan.currency)}/mo
                        <Badge variant="warning" className="text-[11px]">Discount</Badge>
                      </span>
                    ) : (
                      `${formatPrice(plan.price_minor, plan.currency)}/mo`
                    )}
                  </TableCell>
                  <TableCell className="text-sm">{plan.monthly_call_quota.toLocaleString()}</TableCell>
                  <TableCell className="text-sm">{plan.max_concurrent_calls}</TableCell>
                  <TableCell className="text-sm">
                    {plan.credits_per_month.toLocaleString()} @ {plan.credit_price_cents}¢
                  </TableCell>
                  <TableCell>
                    <div className="flex max-w-52 flex-wrap gap-1">
                      {Object.keys(plan.features ?? {}).length === 0 ? (
                        <span className="text-xs text-muted-foreground">—</span>
                      ) : (
                        Object.entries(plan.features).map(([key, value]) => (
                          <Badge key={key} variant="muted" className="text-[11px]">
                            {key}: {String(value)}
                          </Badge>
                        ))
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={plan.is_active ? "success" : "muted"}>{plan.is_active ? "Active" : "Inactive"}</Badge>
                  </TableCell>
                  <TableCell className="pr-5 text-right">
                    <Button variant="ghost" size="sm" onClick={() => setEditingPlan(plan)}>
                      <Pencil className="h-3.5 w-3.5" /> Edit
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      <Dialog open={!!editingPlan} onOpenChange={(open) => !open && setEditingPlan(null)}>
        {editingPlan && <PlanFormDialogContent plan={editingPlan} onDone={() => setEditingPlan(null)} />}
      </Dialog>
    </div>
  );
}

function PlanFormDialogContent({ plan, onDone }: { plan?: PlatformPlan; onDone: () => void }) {
  const [form, setForm] = useState<PlanFormState>(() => (plan ? formFromPlan(plan) : emptyForm()));
  const [deactivateConfirmOpen, setDeactivateConfirmOpen] = useState(false);
  const create = useCreatePlatformPlan();
  const update = useUpdatePlatformPlan();
  const submitting = create.isPending || update.isPending;

  useEffect(() => {
    setForm(plan ? formFromPlan(plan) : emptyForm());
  }, [plan]);

  function updateFeature(index: number, field: "key" | "value", value: string) {
    setForm((f) => ({
      ...f,
      features: f.features.map((row, i) => (i === index ? { ...row, [field]: value } : row)),
    }));
  }

  function addFeatureRow() {
    setForm((f) => ({ ...f, features: [...f.features, { key: "", value: "" }] }));
  }

  function removeFeatureRow(index: number) {
    setForm((f) => ({ ...f, features: f.features.filter((_, i) => i !== index) }));
  }

  function updateBullet(index: number, value: string) {
    setForm((f) => ({ ...f, marketing_bullets: f.marketing_bullets.map((b, i) => (i === index ? value : b)) }));
  }

  function addBulletRow() {
    setForm((f) => ({ ...f, marketing_bullets: [...f.marketing_bullets, ""] }));
  }

  function removeBulletRow(index: number) {
    setForm((f) => ({ ...f, marketing_bullets: f.marketing_bullets.filter((_, i) => i !== index) }));
  }

  async function submit() {
    if (!form.name.trim()) {
      toast.error("Plan name is required");
      return;
    }
    const payload = toPayload(form);
    try {
      if (plan) {
        await update.mutateAsync({ id: plan.id, data: payload });
        toast.success("Plan updated");
      } else {
        await create.mutateAsync(payload);
        toast.success("Plan created");
      }
      onDone();
    } catch (err) {
      toast.error(platformApiErrorMessage(err, plan ? "Couldn't update plan" : "Couldn't create plan"));
    }
  }

  function handleSaveClick() {
    // Deactivating a live plan is financially-impactful (blocks orgs from moving
    // onto it) — confirm before submitting when this edit flips is_active off.
    if (plan && plan.is_active && !form.is_active) {
      setDeactivateConfirmOpen(true);
      return;
    }
    submit();
  }

  return (
    <DialogContent className="max-w-2xl">
      <DialogHeader>
        <DialogTitle>{plan ? "Edit plan" : "Create plan"}</DialogTitle>
      </DialogHeader>
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Name</Label>
            <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          </div>
          <div className="grid grid-cols-[1fr_90px] gap-2">
            <div className="space-y-1.5">
              <Label>Price (minor units)</Label>
              <Input
                type="number"
                min={0}
                value={form.price_minor}
                onChange={(e) => setForm((f) => ({ ...f, price_minor: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Currency</Label>
              <Input value={form.currency} onChange={(e) => setForm((f) => ({ ...f, currency: e.target.value }))} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Discount price (minor units)</Label>
            <Input
              type="number"
              min={0}
              placeholder="No discount"
              value={form.discount_price_minor}
              onChange={(e) => setForm((f) => ({ ...f, discount_price_minor: e.target.value }))}
            />
            <p className="text-xs text-muted-foreground">If set, shown as the sale price with the regular price struck through.</p>
          </div>
          <div className="space-y-1.5">
            <Label>Monthly call quota</Label>
            <Input
              type="number"
              min={0}
              value={form.monthly_call_quota}
              onChange={(e) => setForm((f) => ({ ...f, monthly_call_quota: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Max concurrent calls</Label>
            <Input
              type="number"
              min={0}
              value={form.max_concurrent_calls}
              onChange={(e) => setForm((f) => ({ ...f, max_concurrent_calls: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Credits per month</Label>
            <Input
              type="number"
              min={0}
              value={form.credits_per_month}
              onChange={(e) => setForm((f) => ({ ...f, credits_per_month: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Credit price (cents)</Label>
            <Input
              type="number"
              min={0}
              value={form.credit_price_cents}
              onChange={(e) => setForm((f) => ({ ...f, credit_price_cents: e.target.value }))}
            />
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>Features</Label>
            <Button type="button" variant="outline" size="sm" onClick={addFeatureRow}>
              <Plus className="h-3.5 w-3.5" /> Add
            </Button>
          </div>
          {form.features.length === 0 ? (
            <p className="text-xs text-muted-foreground">No feature flags set on this plan.</p>
          ) : (
            <div className="space-y-2">
              {form.features.map((row, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input
                    placeholder="key"
                    value={row.key}
                    onChange={(e) => updateFeature(i, "key", e.target.value)}
                    className="flex-1"
                  />
                  <Input
                    placeholder="value"
                    value={row.value}
                    onChange={(e) => updateFeature(i, "value", e.target.value)}
                    className="flex-1"
                  />
                  <Button type="button" variant="ghost" size="icon" onClick={() => removeFeatureRow(i)}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-3 rounded-lg border border-border p-3">
          <p className="text-sm font-medium">Pricing page</p>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm">Custom pricing</p>
              <p className="text-xs text-muted-foreground">Shows "Custom" / "Custom volume" and a Contact Sales button instead of a price.</p>
            </div>
            <Switch
              checked={form.is_custom_pricing}
              onCheckedChange={(v) => setForm((f) => ({ ...f, is_custom_pricing: v }))}
            />
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm">Highlighted ("Most Popular")</p>
              <p className="text-xs text-muted-foreground">Badges this plan and gives it the accent border on the pricing page.</p>
            </div>
            <Switch
              checked={form.is_highlighted}
              onCheckedChange={(v) => setForm((f) => ({ ...f, is_highlighted: v }))}
            />
          </div>
          <div className="space-y-2 border-t border-border/60 pt-3">
            <div className="flex items-center justify-between">
              <Label>Marketing bullets</Label>
              <Button type="button" variant="outline" size="sm" onClick={addBulletRow}>
                <Plus className="h-3.5 w-3.5" /> Add
              </Button>
            </div>
            {form.marketing_bullets.length === 0 ? (
              <p className="text-xs text-muted-foreground">No bullets — the pricing card will show just price and minutes.</p>
            ) : (
              <div className="space-y-2">
                {form.marketing_bullets.map((bullet, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <Input
                      placeholder="e.g. 24/7 inbound call handling"
                      value={bullet}
                      onChange={(e) => updateBullet(i, e.target.value)}
                      className="flex-1"
                    />
                    <Button type="button" variant="ghost" size="icon" onClick={() => removeBulletRow(i)}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between rounded-lg border border-border p-3">
          <div>
            <p className="text-sm font-medium">Plan active</p>
            <p className="text-xs text-muted-foreground">Inactive plans can't be assigned to organizations.</p>
          </div>
          <Switch checked={form.is_active} onCheckedChange={(v) => setForm((f) => ({ ...f, is_active: v }))} />
        </div>
      </div>
      <DialogFooter>
        <Button variant="gradient" onClick={handleSaveClick} disabled={submitting}>
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          {plan ? "Save changes" : "Create plan"}
        </Button>
      </DialogFooter>

      <ConfirmDialog
        open={deactivateConfirmOpen}
        onOpenChange={setDeactivateConfirmOpen}
        title="Deactivate this plan?"
        description="Organizations already on this plan are unaffected, but no one will be able to move onto it while it's inactive."
        confirmLabel="Deactivate"
        variant="destructive"
        loading={submitting}
        onConfirm={() => {
          setDeactivateConfirmOpen(false);
          submit();
        }}
      />
    </DialogContent>
  );
}
