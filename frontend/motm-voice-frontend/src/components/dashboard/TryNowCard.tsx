import { useState } from "react";
import { Loader2, PhoneCall, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { agentsApi, apiErrorMessage } from "@/lib/api";

export function TryNowCard() {
  const [phone, setPhone] = useState("+91");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCall() {
    setError(null);
    setLoading(true);
    try {
      await agentsApi.tryNow(phone);
      toast.success("Calling you now — pick up in a few seconds!");
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't place the call"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="card-top-accent">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-4 w-4 text-primary" /> Try Now
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 pt-0">
        <p className="text-sm text-muted-foreground">
          It's free — hear how QuickHowl actually sounds. Enter your number and get a call in seconds.
        </p>
        {error && (
          <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <Input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+91 98765 43210"
            className="flex-1"
          />
          <Button variant="gradient" onClick={handleCall} disabled={loading || phone.trim().length < 8}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <PhoneCall className="h-4 w-4" />}
            Call me
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
