import { PageHeader } from "@/components/shared/PageHeader";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { EmptyState } from "@/components/shared/EmptyState";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePlatformPlans } from "@/lib/platformHooks";

function formatPrice(priceMinor: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(priceMinor / 100);
}

// Read-only by design: plan creation/pricing changes go through engineering
// now rather than being editable live from the SuperAdmin panel, so there's
// no create/edit UI here on purpose -- just a list to see what's configured.
export default function PlatformPlans() {
  const plans = usePlatformPlans();

  return (
    <div className="space-y-6">
      <PageHeader title="Plans" description="Billing plans available to organizations." />

      {plans.isError ? (
        <ErrorBanner error={plans.error} onRetry={() => plans.refetch()} />
      ) : plans.isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : !plans.data || plans.data.length === 0 ? (
        <EmptyState title="No plans yet" description="No billing plans are configured." />
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
                <TableHead className="pr-5">Status</TableHead>
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
                  <TableCell className="pr-5">
                    <Badge variant={plan.is_active ? "success" : "muted"}>{plan.is_active ? "Active" : "Inactive"}</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}
