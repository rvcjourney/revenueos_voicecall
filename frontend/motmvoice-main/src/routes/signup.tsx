import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { AuthLayout } from "@/components/marketing/AuthLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { authApi } from "@/lib/api";
import { toast } from "sonner";

export const Route = createFileRoute("/signup")({
  head: () => ({ meta: [{ title: "Join Team — MOTMVoice" }] }),
  component: SignupPage,
});

function SignupPage() {
  const [form, setForm] = useState({ name: "", email: "", password: "", confirm: "", org_code: "" });
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  function set<K extends keyof typeof form>(k: K, v: string) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!form.name || !form.email || !form.org_code) return setErr("Please fill all required fields");
    if (form.password.length < 6) return setErr("Password must be at least 6 characters");
    if (form.password !== form.confirm) return setErr("Passwords do not match");

    setLoading(true);
    try {
      await authApi.registerMember({
        full_name: form.name,
        email: form.email,
        password: form.password,
        org_code: form.org_code.trim().toUpperCase(),
      });
      // Log them in immediately after registration
      await login(form.email, form.password);
      toast.success("Welcome! Your account is ready.");
      navigate({ to: "/dashboard" });
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Registration failed. Check your invite code.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title="Join your team" subtitle="Enter your invite code from your admin to get started">
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="name">Full Name *</Label>
          <Input id="name" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Priya Sharma" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="email">Work Email *</Label>
          <Input id="email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} placeholder="priya@yourcompany.com" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="org_code">Team Invite Code *</Label>
          <Input
            id="org_code"
            value={form.org_code}
            onChange={(e) => set("org_code", e.target.value.toUpperCase())}
            placeholder="8-character code from your admin"
            className="font-mono tracking-widest"
            maxLength={8}
          />
          <p className="text-xs text-muted-foreground">Ask your admin for this code (visible on their Team page).</p>
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
        {err && <p className="text-sm text-destructive">{err}</p>}
        <Button type="submit" disabled={loading} className="w-full bg-gradient-primary text-white shadow-glow">
          {loading ? "Creating account…" : "Join Team"}
        </Button>
        <p className="text-center text-sm text-muted-foreground pt-2">
          Already have an account?{" "}
          <Link to="/login" className="text-primary hover:underline">Sign in</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
