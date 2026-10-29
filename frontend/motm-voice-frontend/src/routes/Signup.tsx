import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useForm, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import axios from "axios";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { AuthLayout } from "@/components/marketing/AuthLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PlanPicker } from "@/components/billing/PlanPicker";
import { BillingAddressForm } from "@/components/billing/BillingAddressForm";
import { OtpEntry } from "@/components/auth/OtpEntry";
import { GoogleButton } from "@/components/auth/GoogleButton";
import { useAuth } from "@/lib/auth";
import { apiErrorMessage, authApi } from "@/lib/api";
import { useBillingAddress, useCheckout, useVerifyPayment } from "@/lib/hooks";
import { openRazorpayCheckout } from "@/lib/razorpayCheckout";
import type { PublicPlan } from "@/lib/types";

const memberSchema = z.object({
  full_name: z.string().min(2, "Enter your full name"),
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(6, "Password must be at least 6 characters"),
  org_code: z.string().min(8, "Invite codes are 8 characters").max(8, "Invite codes are 8 characters"),
});
type MemberValues = z.infer<typeof memberSchema>;

const orgSchema = z.object({
  full_name: z.string().min(2, "Enter your full name"),
  company_name: z.string().min(2, "Enter your company name"),
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(6, "Password must be at least 6 characters"),
  phone: z.string().min(10, "Enter a valid phone number"),
});
type OrgValues = z.infer<typeof orgSchema>;

/** Set by routes/GoogleCallback when a Google account has no QuickHowl account yet. */
type GoogleSignup = { signup_token: string; email: string; full_name: string };

export default function Signup() {
  const [tab, setTab] = useState("org");
  const google = (useLocation().state as { google?: GoogleSignup } | null)?.google;

  return (
    <AuthLayout wide title="Create your account" subtitle="Get your AI voice agents making calls in minutes.">
      {google ? (
        <p className="rounded-lg border bg-muted/40 px-3 py-2 text-sm">
          Signing up with Google as <span className="font-medium">{google.email}</span>. Just a few details to
          finish.
        </p>
      ) : (
        <GoogleButton label="Sign up with Google" />
      )}
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="w-full">
          <TabsTrigger value="org" className="flex-1">
            Create organization
          </TabsTrigger>
          <TabsTrigger value="join" className="flex-1">
            Join a team
          </TabsTrigger>
        </TabsList>

        <TabsContent value="join">
          <p className="mb-3 text-xs text-muted-foreground">
            Have an 8-character invite code from your admin? Join their existing QuickHowl workspace.
          </p>
          <JoinTeamForm google={google} />
        </TabsContent>

        <TabsContent value="org">
          <p className="mb-3 text-xs text-muted-foreground">
            Setting up QuickHowl for your company for the first time? Create a new organization.
          </p>
          <CreateOrgForm google={google} />
        </TabsContent>
      </Tabs>

      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-primary hover:underline">
          Log in
        </Link>
      </p>
    </AuthLayout>
  );
}

function JoinTeamForm({ google }: { google?: GoogleSignup }) {
  const { registerMember, verifyOtp, setSession } = useAuth();
  const navigate = useNavigate();

  const [serverError, setServerError] = useState<string | null>(null);
  const [step, setStep] = useState<"form" | "otp">("form");
  const [memberValues, setMemberValues] = useState<MemberValues | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<MemberValues>({
    // Google already gave us a verified email, so no email/password fields.
    resolver: (google
      ? zodResolver(memberSchema.omit({ email: true, password: true }))
      : zodResolver(memberSchema)) as Resolver<MemberValues>,
    defaultValues: { full_name: google?.full_name ?? "" },
  });

  async function onSubmit(values: MemberValues) {
    setServerError(null);
    const normalized = { ...values, org_code: values.org_code.toUpperCase() };
    try {
      if (google) {
        const res = await authApi.googleComplete({
          signup_token: google.signup_token,
          full_name: normalized.full_name,
          org_code: normalized.org_code,
        });
        setSession(res.data);
        toast.success(`Welcome, ${normalized.full_name}!`);
        navigate("/dashboard");
        return;
      }
      await registerMember(normalized);
      setMemberValues(normalized);
      setStep("otp");
      toast.success(`Check ${normalized.email} for a verification code.`);
    } catch (err) {
      setServerError(apiErrorMessage(err, "Couldn't join that team. Double-check the invite code."));
    }
  }

  async function onOtpVerified() {
    toast.success(`Welcome, ${memberValues?.full_name}!`);
    navigate("/dashboard");
  }

  if (step === "otp" && memberValues) {
    return <OtpEntry email={memberValues.email} verifyOtp={verifyOtp} onVerified={onOtpVerified} />;
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="grid gap-3 sm:grid-cols-2">
      {serverError && (
        <div className="sm:col-span-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {serverError}
        </div>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="join-name">Full name</Label>
        <Input id="join-name" placeholder="Priya Mehta" {...register("full_name")} />
        {errors.full_name && <p className="text-xs text-destructive">{errors.full_name.message}</p>}
      </div>
      {!google && (
        <>
          <div className="space-y-1.5">
            <Label htmlFor="join-email">Email address</Label>
            <Input id="join-email" type="email" placeholder="you@company.com" {...register("email")} />
            {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="join-password">Password</Label>
            <Input id="join-password" type="password" placeholder="Min. 6 characters" {...register("password")} />
            {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
          </div>
        </>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="join-code">Team invite code</Label>
        <Input id="join-code" placeholder="A1B2C3D4" maxLength={8} className="uppercase tracking-widest" {...register("org_code")} />
        {errors.org_code && <p className="text-xs text-destructive">{errors.org_code.message}</p>}
        <p className="text-xs text-muted-foreground">Ask your admin for this — it's on their Team page.</p>
      </div>
      <Button type="submit" variant="gradient" className="w-full sm:col-span-2" size="lg" disabled={isSubmitting}>
        {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
        Join team
      </Button>
    </form>
  );
}

function CreateOrgForm({ google }: { google?: GoogleSignup }) {
  const { registerOrg, verifyOtp, setSession } = useAuth();
  const navigate = useNavigate();
  const checkout = useCheckout();
  const verifyPayment = useVerifyPayment();
  const qc = useQueryClient();
  const billingAddress = useBillingAddress();

  const [serverError, setServerError] = useState<string | null>(null);
  const [emailTaken, setEmailTaken] = useState(false);
  const [step, setStep] = useState<"form" | "otp" | "plan">("form");
  const [orgValues, setOrgValues] = useState<OrgValues | null>(null);
  const [selectedPlan, setSelectedPlan] = useState<PublicPlan | null>(null);
  const [paying, setPaying] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<OrgValues>({
    resolver: (google
      ? zodResolver(orgSchema.omit({ email: true, password: true }))
      : zodResolver(orgSchema)) as Resolver<OrgValues>,
    defaultValues: { full_name: google?.full_name ?? "" },
  });

  async function onSubmit(values: OrgValues) {
    setServerError(null);
    setEmailTaken(false);
    try {
      if (google) {
        // Google verified the email, so straight to picking a plan (no OTP).
        const res = await authApi.googleComplete({
          signup_token: google.signup_token,
          full_name: values.full_name,
          company_name: values.company_name,
          phone: values.phone,
        });
        setSession(res.data);
        setOrgValues({ ...values, email: google.email });
        setStep("plan");
        toast.success(`Welcome, ${values.full_name}! Pick a plan to activate ${values.company_name}.`);
        return;
      }
      await registerOrg(values);
      setOrgValues(values);
      setStep("otp");
      toast.success(`Check ${values.email} for a verification code.`);
    } catch (err) {
      // /register's only 409 case is "this email already has an account" —
      // show that directly instead of a generic error, with a way out.
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        setEmailTaken(true);
        return;
      }
      setServerError(apiErrorMessage(err, "Couldn't create your organization."));
    }
  }

  async function onOtpVerified() {
    if (!orgValues) return;
    setStep("plan");
    toast.success(`Welcome, ${orgValues.full_name}! Pick a plan to activate ${orgValues.company_name}.`);
  }

  async function startPayment() {
    if (!selectedPlan) {
      toast.error("Pick a plan first");
      return;
    }
    setPaying(true);
    try {
      const result = await checkout.mutateAsync(selectedPlan.id);
      if (result.action === "new" && result.subscription_id && result.razorpay_key_id) {
        await openRazorpayCheckout({
          key: result.razorpay_key_id,
          subscription_id: result.subscription_id,
          name: "QuickHowl",
          description: `${result.plan_name} plan`,
          prefill: { name: orgValues?.full_name, email: orgValues?.email, contact: orgValues?.phone },
          theme: { color: "#2563eb" },
          handler: async (response) => {
            try {
              await verifyPayment.mutateAsync(response);
            } finally {
              toast.success("Payment received — activating your account...");
              navigate("/dashboard");
            }
          },
          modal: {
            ondismiss: () => setPaying(false),
          },
        });
      } else {
        // action:"change" completes synchronously server-side — safe to
        // reflect immediately (in practice unreachable for a brand-new org,
        // which never has an existing subscription to change).
        await qc.invalidateQueries({ queryKey: ["billing-current"] });
        toast.success("Plan updated");
        navigate("/dashboard");
      }
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't start checkout"));
      setPaying(false);
    }
  }

  if (step === "otp" && orgValues) {
    return <OtpEntry email={orgValues.email} verifyOtp={verifyOtp} onVerified={onOtpVerified} />;
  }

  if (step === "plan") {
    return (
      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Pick a plan to activate your organization. You're signed in already — you can also do this later from
          Billing.
        </p>
        <PlanPicker selectedPlanId={selectedPlan?.id ?? null} onSelect={setSelectedPlan} />
        {!billingAddress.isLoading && !billingAddress.data?.state ? (
          <BillingAddressForm onSaved={() => billingAddress.refetch()} />
        ) : (
          <Button
            variant="gradient"
            className="w-full"
            size="lg"
            onClick={startPayment}
            disabled={!selectedPlan || paying}
          >
            {paying && <Loader2 className="h-4 w-4 animate-spin" />}
            Continue to payment
          </Button>
        )}
        <Button variant="ghost" className="w-full" onClick={() => navigate("/dashboard")}>
          Skip for now
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="grid gap-3 sm:grid-cols-2">
      {emailTaken && (
        <div className="sm:col-span-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          This email is already registered.{" "}
          <Link to="/login" className="font-medium underline">
            Log in
          </Link>{" "}
          instead — if you never finished verifying it, the login page will let you re-enter your code.
        </div>
      )}
      {serverError && (
        <div className="sm:col-span-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {serverError}
        </div>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="org-name">Full name</Label>
        <Input id="org-name" placeholder="Priya Mehta" {...register("full_name")} />
        {errors.full_name && <p className="text-xs text-destructive">{errors.full_name.message}</p>}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="org-company">Company name</Label>
        <Input id="org-company" placeholder="Acme Sales Pvt Ltd" {...register("company_name")} />
        {errors.company_name && <p className="text-xs text-destructive">{errors.company_name.message}</p>}
      </div>
      {!google && (
        <>
          <div className="space-y-1.5">
            <Label htmlFor="org-email">Email address</Label>
            <Input id="org-email" type="email" placeholder="you@company.com" {...register("email")} />
            {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="org-password">Password</Label>
            <Input id="org-password" type="password" placeholder="Min. 6 characters" {...register("password")} />
            {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
          </div>
        </>
      )}
      <div className="space-y-1.5 sm:col-span-2">
        <Label htmlFor="org-phone">Phone</Label>
        <Input id="org-phone" placeholder="+91 98765 43210" {...register("phone")} />
        {errors.phone && <p className="text-xs text-destructive">{errors.phone.message}</p>}
      </div>
      <Button type="submit" variant="gradient" className="w-full sm:col-span-2" size="lg" disabled={isSubmitting}>
        {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
        Create organization
      </Button>
    </form>
  );
}
