import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiErrorMessage, authApi } from "@/lib/api";

export function OtpEntry({
  email,
  verifyOtp,
  onVerified,
}: {
  email: string;
  verifyOtp: (email: string, code: string) => Promise<unknown>;
  onVerified: () => void | Promise<void>;
}) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const t = setInterval(() => setResendCooldown((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, [resendCooldown]);

  async function handleVerify() {
    setError(null);
    setVerifying(true);
    try {
      await verifyOtp(email, code);
      await onVerified();
    } catch (err) {
      setError(apiErrorMessage(err, "That code is incorrect or has expired."));
    } finally {
      setVerifying(false);
    }
  }

  async function handleResend() {
    if (resendCooldown > 0) return;
    try {
      await authApi.resendOtp(email);
      toast.success("Code resent — check your email.");
      setResendCooldown(60);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't resend the code."));
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        We sent a verification code to <span className="font-medium text-foreground">{email}</span>. Enter it below
        to continue.
      </p>
      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="otp-code">Verification code</Label>
        <Input
          id="otp-code"
          inputMode="numeric"
          maxLength={6}
          placeholder="123456"
          className="text-center text-lg tracking-[0.5em]"
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
        />
      </div>
      <Button
        variant="gradient"
        className="w-full"
        size="lg"
        onClick={handleVerify}
        disabled={verifying || code.length < 6}
      >
        {verifying && <Loader2 className="h-4 w-4 animate-spin" />}
        Verify email
      </Button>
      <Button variant="ghost" className="w-full" onClick={handleResend} disabled={resendCooldown > 0}>
        {resendCooldown > 0 ? `Resend code in ${resendCooldown}s` : "Resend code"}
      </Button>
    </div>
  );
}
