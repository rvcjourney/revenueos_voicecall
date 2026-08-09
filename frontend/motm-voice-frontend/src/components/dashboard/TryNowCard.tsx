import { useState } from "react";
import { Loader2, PhoneCall, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { agentsApi, apiErrorMessage } from "@/lib/api";

export function TryNowCard() {
  const [open, setOpen] = useState(false);
  const [phone, setPhone] = useState("+91");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCall() {
    setError(null);
    setLoading(true);
    try {
      await agentsApi.tryNow(phone);
      toast.success("Calling you now — pick up in a few seconds!");
      setOpen(false);
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't place the call"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          type="button"
          className="card-top-accent hover-lift group flex w-full items-center justify-between gap-3 rounded-2xl border border-border bg-card px-4 py-3 text-left shadow-[var(--shadow-card)] transition-colors hover:border-primary/40"
        >
          <span className="flex min-w-0 items-center gap-2.5">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
              <Sparkles className="h-4 w-4" />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold">Try Now</span>
              <span className="block truncate text-xs text-muted-foreground">
                Free — hear how QuickHowl actually sounds
              </span>
            </span>
          </span>
          <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-primary/15 px-3 py-1.5 text-xs font-medium text-primary transition-colors group-hover:bg-primary/25">
            <PhoneCall className="h-3.5 w-3.5" /> Call me
          </span>
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" /> Try Now
          </DialogTitle>
          <DialogDescription>
            It's free — hear how QuickHowl actually sounds. Enter your number and get a call in seconds.
          </DialogDescription>
        </DialogHeader>
        {error && (
          <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
        <Input
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="+91 98765 43210"
          autoFocus
        />
        <Button
          variant="gradient"
          onClick={handleCall}
          disabled={loading || phone.trim().length < 8}
          className="w-full"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <PhoneCall className="h-4 w-4" />}
          Call me
        </Button>
      </DialogContent>
    </Dialog>
  );
}
