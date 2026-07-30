import type { LucideIcon } from "lucide-react";
import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Sparkline } from "@/components/charts/Sparkline";
import { cn } from "@/lib/utils";

interface StatCardDelta {
  /** Signed percentage or absolute change, e.g. +12.4 or -3. */
  value: number;
  /** What the delta is measured against, e.g. "vs yesterday". */
  periodLabel: string;
  /** Which direction counts as good. Defaults to "up". */
  goodDirection?: "up" | "down";
  /** Render as a raw count instead of a percentage. */
  isPercent?: boolean;
}

interface StatCardProps {
  icon?: LucideIcon;
  label: string;
  value: string | number | undefined;
  loading?: boolean;
  delta?: StatCardDelta;
  trend?: number[];
  tone?: "default" | "success" | "warning" | "info";
  className?: string;
}

const toneClasses: Record<NonNullable<StatCardProps["tone"]>, string> = {
  default: "bg-primary/12 text-primary",
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  info: "bg-info/15 text-info",
};

export function StatCard({ icon: Icon, label, value, loading, delta, trend, tone = "default", className }: StatCardProps) {
  return (
    <Card className={cn("relative overflow-hidden p-5", className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          {loading || value === undefined ? (
            <Skeleton className="mt-2 h-8 w-20" />
          ) : (
            <p className="stat-figure mt-1 text-3xl font-semibold text-foreground">{value}</p>
          )}
        </div>
        {Icon && (
          <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-xl", toneClasses[tone])}>
            <Icon className="h-4.5 w-4.5" />
          </span>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between gap-3">
        {delta ? <DeltaTag delta={delta} /> : <span />}
        {trend && trend.length > 1 && !loading && (
          <Sparkline data={trend} color="var(--color-primary)" className="h-8 w-20" />
        )}
      </div>
    </Card>
  );
}

function DeltaTag({ delta }: { delta: StatCardDelta }) {
  const { value, periodLabel, goodDirection = "up", isPercent = true } = delta;
  const direction = value > 0 ? "up" : value < 0 ? "down" : "flat";
  const isGood = direction === "flat" ? null : direction === goodDirection;

  const Icon = direction === "up" ? ArrowUp : direction === "down" ? ArrowDown : Minus;
  const colorClass =
    isGood === null ? "text-muted-foreground" : isGood ? "text-success" : "text-destructive";

  const formatted = `${value > 0 ? "+" : ""}${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${isPercent ? "%" : ""}`;

  return (
    <span className={cn("inline-flex items-center gap-1 text-xs font-medium", colorClass)}>
      <Icon className="h-3 w-3" />
      {formatted}
      <span className="font-normal text-muted-foreground">{periodLabel}</span>
    </span>
  );
}
