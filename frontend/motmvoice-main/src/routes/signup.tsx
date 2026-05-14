import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { AuthLayout } from "@/components/marketing/AuthLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";

export const Route = createFileRoute("/signup")({
  head: () => ({ meta: [{ title: "Create account — MOTMVoice" }] }),
  component: SignupPage,
});

function SignupPage() {
  const [form, setForm] = useState({ name: "", company: "", email: "", phone: "", password: "", confirm: "", terms: false });
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  function set<K extends keyof typeof form>(k: K, v: (typeof form)[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!form.name || !form.email || !form.company) return setErr("Please fill all required fields");
    if (form.password.length < 6) return setErr("Password must be at least 6 characters");
    if (form.password !== form.confirm) return setErr("Passwords do not match");
    if (!form.terms) return setErr("Please accept the terms");

    setLoading(true);
    try {
      await register({
        full_name: form.name,
        company_name: form.company,
        email: form.email,
        password: form.password,
        phone: form.phone,
      });
      toast.success("Account created! Welcome aboard.");
      navigate({ to: "/dashboard" });
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title="Create your account" subtitle="Start running AI voice calls in under 5 minutes">
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="name">Full name *</Label>
            <Input id="name" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Aniket Sharma" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="company">Company *</Label>
            <Input id="company" value={form.company} onChange={(e) => set("company", e.target.value)} placeholder="Baba Valves" />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="email">Work email *</Label>
          <Input id="email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="phone">Phone</Label>
          <Input id="phone" value={form.phone} onChange={(e) => set("phone", e.target.value)} placeholder="+91 98765 43210" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="password">Password *</Label>
            <Input id="password" type="password" value={form.password} onChange={(e) => set("password", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="confirm">Confirm *</Label>
            <Input id="confirm" type="password" value={form.confirm} onChange={(e) => set("confirm", e.target.value)} />
          </div>
        </div>
        <div className="flex items-start gap-2">
          <Checkbox id="terms" checked={form.terms} onCheckedChange={(v) => set("terms", !!v)} />
          <Label htmlFor="terms" className="text-sm font-normal leading-relaxed">
            I agree to the <a className="text-primary hover:underline" href="#">Terms</a> and <a className="text-primary hover:underline" href="#">Privacy Policy</a>
          </Label>
        </div>
        {err && <p className="text-sm text-destructive">{err}</p>}
        <Button type="submit" disabled={loading} className="w-full bg-gradient-primary text-white shadow-glow">
          {loading ? "Creating account…" : "Create Account"}
        </Button>
        <p className="text-center text-sm text-muted-foreground pt-2">
          Already have an account?{" "}
          <Link to="/login" className="text-primary hover:underline">Sign in</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
