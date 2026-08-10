import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { AuthLayout } from "@/components/marketing/AuthLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiErrorMessage, authApi } from "@/lib/api";

const emailSchema = z.object({
  email: z.string().email("Enter a valid email address"),
});
type EmailValues = z.infer<typeof emailSchema>;

const resetSchema = z.object({
  code: z.string().min(6, "Enter the code from your email"),
  new_password: z.string().min(6, "Password must be at least 6 characters"),
});
type ResetValues = z.infer<typeof resetSchema>;

export default function ForgotPassword() {
  const navigate = useNavigate();
  const [email, setEmail] = useState<string | null>(null);

  return (
    <AuthLayout
      title={email ? "Reset your password" : "Forgot password?"}
      subtitle={
        email
          ? `Enter the code sent to ${email} and choose a new password.`
          : "Enter your email and we'll send you a reset code."
      }
    >
      {email ? (
        <ResetForm email={email} onDone={() => navigate("/login")} />
      ) : (
        <RequestCodeForm onSent={setEmail} />
      )}
      <p className="text-center text-sm text-muted-foreground">
        <Link to="/login" className="font-medium text-primary hover:underline">
          Back to login
        </Link>
      </p>
    </AuthLayout>
  );
}

function RequestCodeForm({ onSent }: { onSent: (email: string) => void }) {
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<EmailValues>({ resolver: zodResolver(emailSchema) });

  async function onSubmit(values: EmailValues) {
    setServerError(null);
    try {
      await authApi.forgotPassword(values.email);
      onSent(values.email);
    } catch (err) {
      setServerError(apiErrorMessage(err, "Couldn't send a reset code."));
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {serverError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {serverError}
        </div>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="fp-email">Email address</Label>
        <Input id="fp-email" type="email" placeholder="you@company.com" {...register("email")} />
        {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
      </div>
      <Button type="submit" variant="gradient" className="w-full" size="lg" disabled={isSubmitting}>
        {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
        Send reset code
      </Button>
    </form>
  );
}

function ResetForm({ email, onDone }: { email: string; onDone: () => void }) {
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResetValues>({ resolver: zodResolver(resetSchema) });

  async function onSubmit(values: ResetValues) {
    setServerError(null);
    try {
      await authApi.resetPassword(email, values.code, values.new_password);
      toast.success("Password reset — log in with your new password.");
      onDone();
    } catch (err) {
      setServerError(apiErrorMessage(err, "Couldn't reset your password."));
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {serverError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {serverError}
        </div>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="rp-code">Reset code</Label>
        <Input
          id="rp-code"
          inputMode="numeric"
          maxLength={10}
          placeholder="123456"
          className="text-center text-lg tracking-[0.35em]"
          {...register("code")}
        />
        {errors.code && <p className="text-xs text-destructive">{errors.code.message}</p>}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="rp-password">New password</Label>
        <Input id="rp-password" type="password" placeholder="Min. 6 characters" {...register("new_password")} />
        {errors.new_password && <p className="text-xs text-destructive">{errors.new_password.message}</p>}
      </div>
      <Button type="submit" variant="gradient" className="w-full" size="lg" disabled={isSubmitting}>
        {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
        Reset password
      </Button>
    </form>
  );
}
