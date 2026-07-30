import { useAuth } from "@/lib/auth";
import { useConcurrency, useOrgInfo } from "@/lib/hooks";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { initials, cn } from "@/lib/utils";

export function TopBar() {
  const { user } = useAuth();
  const orgInfo = useOrgInfo();
  const concurrency = useConcurrency();

  const today = new Date().toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });

  const liveCalls = concurrency.data?.in_use ?? 0;
  const isLive = liveCalls > 0;

  return (
    <header className="flex shrink-0 items-center justify-between gap-4 rounded-2xl border border-border bg-card px-5 py-3.5 shadow-[var(--shadow-card)]">
      <div className="flex min-w-0 items-center gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">Workspace</p>
          <p className="truncate text-sm font-semibold text-foreground">{user?.org_name}</p>
        </div>
        {orgInfo.data && (
          <span className="hidden shrink-0 rounded-full border border-border bg-muted px-2.5 py-1 text-[11px] font-medium capitalize text-muted-foreground sm:inline-flex">
            {orgInfo.data.plan_tier} plan
          </span>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-3 sm:gap-4">
        <span
          className={cn(
            "hidden items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium sm:flex",
            isLive ? "bg-success/15 text-success" : "bg-muted text-muted-foreground"
          )}
        >
          <span className={cn("h-1.5 w-1.5 rounded-full bg-current", isLive && "animate-pulse-glow")} />
          {isLive ? `${liveCalls} live call${liveCalls === 1 ? "" : "s"}` : "All quiet"}
        </span>
        <span className="hidden text-xs text-muted-foreground sm:block">{today}</span>
        <div className="hidden h-6 w-px bg-border sm:block" />
        <ThemeToggle />
        <Avatar className="h-8 w-8">
          <AvatarFallback className="bg-[image:var(--gradient-primary)] text-primary-foreground">
            {initials(user?.full_name ?? "?")}
          </AvatarFallback>
        </Avatar>
      </div>
    </header>
  );
}
