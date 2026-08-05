import { AlertTriangle, RefreshCw, WifiOff } from "lucide-react";
import { isNetworkError, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ErrorBannerProps {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}

export function ErrorBanner({ error, onRetry, className }: ErrorBannerProps) {
  const offline = isNetworkError(error);
  return (
    <div
      className={cn(
        "flex flex-col items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm sm:flex-row sm:items-center sm:justify-between",
        className
      )}
    >
      <div className="flex items-start gap-3">
        {offline ? (
          <WifiOff className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        ) : (
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        )}
        <div>
          <p className="font-medium text-destructive">{offline ? "Can't reach QuickHowl" : "Something went wrong"}</p>
          <p className="text-muted-foreground">{apiErrorMessage(error)}</p>
        </div>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} className="shrink-0">
          <RefreshCw className="h-3.5 w-3.5" />
          Retry
        </Button>
      )}
    </div>
  );
}
