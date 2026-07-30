import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import axios from "axios";
import { Loader2, Mail } from "lucide-react";
import { toast } from "sonner";
import { AuthLayout } from "@/components/marketing/AuthLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth";
import { apiErrorMessage } from "@/lib/api";
import { authApi } from "@/lib/api";

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
  phone: z.string().optional(),
});
type OrgValues = z.infer<typeof orgSchema>;

export default function Signup() {
  const { registerMember } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState("join");

  return (
    <AuthLayout title="Create your account" subtitle="Get your AI voice agents making calls in minutes.">
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="w-full">
          <TabsTrigger value="join" className="flex-1">
            Join a team
          </TabsTrigger>
          <TabsTrigger value="org" className="flex-1">
            Create organization
          </TabsTrigger>
        </TabsList>

        <TabsContent value="join">
          <p className="mb-4 text-xs text-muted-foreground">
            Have an 8-character invite code from your admin? Join their existing Talkryn workspace.
          </p>
          <JoinTeamForm
            onSuccess={async (values) => {
              const user = await registerMember(values);
              toast.success(`Welcome to ${user.org_name}!`);
              navigate("/dashboard");
            }}
          />
        </TabsContent>

        <TabsContent value="org">
          <p className="mb-4 text-xs text-muted-foreground">
            Setting up Talkryn for your company for the first time? Create a new organization.
          </p>
          <CreateOrgForm />
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

function JoinTeamForm({ onSuccess }: { onSuccess: (values: MemberValues) => Promise<void> }) {
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<MemberValues>({ resolver: zodResolver(memberSchema) });

  async function onSubmit(values: MemberValues) {
    setServerError(null);
    try {
      await onSuccess({ ...values, org_code: values.org_code.toUpperCase() });
    } catch (err) {
      setServerError(apiErrorMessage(err, "Couldn't join that team. Double-check the invite code."));
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
        <Label htmlFor="join-name">Full name</Label>
        <Input id="join-name" placeholder="Priya Mehta" {...register("full_name")} />
        {errors.full_name && <p className="text-xs text-destructive">{errors.full_name.message}</p>}
      </div>
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
      <div className="space-y-1.5">
        <Label htmlFor="join-code">Team invite code</Label>
        <Input id="join-code" placeholder="A1B2C3D4" maxLength={8} className="uppercase tracking-widest" {...register("org_code")} />
        {errors.org_code && <p className="text-xs text-destructive">{errors.org_code.message}</p>}
        <p className="text-xs text-muted-foreground">Ask your admin for this — it's on their Team page.</p>
      </div>
      <Button type="submit" variant="gradient" className="w-full" size="lg" disabled={isSubmitting}>
        {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
        Join team
      </Button>
    </form>
  );
}

function CreateOrgForm() {
  const [serverError, setServerError] = useState<string | null>(null);
  const [registrationClosed, setRegistrationClosed] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<OrgValues>({ resolver: zodResolver(orgSchema) });

  async function onSubmit(values: OrgValues) {
    setServerError(null);
    setRegistrationClosed(false);
    try {
      await authApi.register(values);
      toast.success("Organization created — check your email to log in.");
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        setRegistrationClosed(true);
        return;
      }
      setServerError(apiErrorMessage(err, "Couldn't create your organization."));
    }
  }

  if (registrationClosed) {
    return (
      <div className="space-y-4 rounded-xl border border-border bg-muted/40 p-5 text-center">
        <Mail className="mx-auto h-8 w-8 text-primary" />
        <div className="space-y-1">
          <p className="text-sm font-medium">Registration is currently closed</p>
          <p className="text-sm text-muted-foreground">
            New organizations are being onboarded directly by our team right now. Contact your administrator, or reach
            out and we'll get you set up.
          </p>
        </div>
        <Button variant="outline" onClick={() => setRegistrationClosed(false)}>
          Back to form
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {serverError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
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
      <div className="space-y-1.5">
        <Label htmlFor="org-phone">Phone (optional)</Label>
        <Input id="org-phone" placeholder="+91 98765 43210" {...register("phone")} />
      </div>
      <Button type="submit" variant="gradient" className="w-full" size="lg" disabled={isSubmitting}>
        {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
        Create organization
      </Button>
    </form>
  );
}
