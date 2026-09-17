import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Loader2, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { apiErrorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useCompanyProfile, useSaveCompanyProfile } from "@/lib/hooks";
import type { CompanyProfileInput } from "@/lib/types";

const EMPTY: CompanyProfileInput = {
  company_name: "",
  website: "",
  industry: "",
  what_we_offer: "",
  value_proposition: "",
  target_customers: "",
  key_points: "",
  call_objective: "",
  tone_notes: "",
  extra_info: "",
};

type TextField = {
  key: keyof CompanyProfileInput;
  label: string;
  placeholder: string;
  required?: boolean;
  rows?: number;
};

const TEXT_FIELDS: TextField[] = [
  {
    key: "what_we_offer",
    label: "What we offer",
    placeholder: "Our products/services, in plain words. e.g. AI voice agents that call leads in Hindi and English…",
    required: true,
    rows: 4,
  },
  {
    key: "value_proposition",
    label: "Why customers choose us",
    placeholder: "Main benefits. e.g. 10x more calls per day, costs less than one telecaller, live in 2 days…",
    rows: 3,
  },
  {
    key: "target_customers",
    label: "Who we sell to",
    placeholder: "Ideal customers. e.g. Real estate developers, EdTech, insurance agencies with 10+ sales staff…",
    rows: 3,
  },
  {
    key: "key_points",
    label: "Proof points & offers",
    placeholder: "Clients, results, current offers. e.g. Used by 40+ companies; free 7-day trial this month…",
    rows: 3,
  },
  {
    key: "call_objective",
    label: "Goal of each call",
    placeholder: "e.g. Book a 15-minute demo, or get their WhatsApp number to send the brochure",
    rows: 2,
  },
  {
    key: "tone_notes",
    label: "Tone (optional)",
    placeholder: "e.g. Respectful and consultative, never pushy",
    rows: 2,
  },
  {
    key: "extra_info",
    label: "Anything else the AI should know (optional)",
    placeholder: "Pricing rules, things never to promise, FAQs…",
    rows: 4,
  },
];

export default function PrimeCompanyProfile() {
  const { isAdmin } = useAuth();
  const profile = useCompanyProfile();
  const save = useSaveCompanyProfile();
  const [form, setForm] = useState<CompanyProfileInput>(EMPTY);

  useEffect(() => {
    if (!profile.data) return;
    const next = { ...EMPTY };
    for (const key of Object.keys(EMPTY) as (keyof CompanyProfileInput)[]) {
      next[key] = profile.data[key] ?? "";
    }
    setForm(next);
  }, [profile.data]);

  function update(key: keyof CompanyProfileInput, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSave() {
    if (!form.company_name.trim() || !form.what_we_offer?.trim()) {
      toast.error("Company name and 'What we offer' are required");
      return;
    }
    try {
      await save.mutateAsync(form);
      toast.success("Company Profile saved");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't save Company Profile"));
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Button variant="ghost" size="sm" asChild className="-ml-2">
        <Link to="/prime-calling">
          <ArrowLeft className="h-4 w-4" /> Back to Prime Calling
        </Link>
      </Button>

      <PageHeader
        title="Company Profile"
        description="Who you are and what you sell. The AI combines this with each contact's details to write their call."
      />

      {!isAdmin && (
        <p className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
          Only admins can edit the Company Profile.
        </p>
      )}

      {profile.isError ? (
        <ErrorBanner error={profile.error} onRetry={() => profile.refetch()} />
      ) : profile.isLoading ? (
        <Skeleton className="h-[600px] w-full" />
      ) : (
        <Card>
          <CardContent className="space-y-5 pt-6">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="cp-name">Company name *</Label>
                <Input
                  id="cp-name"
                  value={form.company_name}
                  disabled={!isAdmin}
                  onChange={(e) => update("company_name", e.target.value)}
                  placeholder="Acme Technologies"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="cp-industry">Industry</Label>
                <Input
                  id="cp-industry"
                  value={form.industry ?? ""}
                  disabled={!isAdmin}
                  onChange={(e) => update("industry", e.target.value)}
                  placeholder="SaaS / Voice AI"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cp-website">Website</Label>
              <Input
                id="cp-website"
                value={form.website ?? ""}
                disabled={!isAdmin}
                onChange={(e) => update("website", e.target.value)}
                placeholder="https://acme.com"
              />
            </div>

            {TEXT_FIELDS.map((f) => (
              <div key={f.key} className="space-y-1.5">
                <Label htmlFor={`cp-${f.key}`}>
                  {f.label}
                  {f.required ? " *" : ""}
                </Label>
                <Textarea
                  id={`cp-${f.key}`}
                  rows={f.rows}
                  value={form[f.key] ?? ""}
                  disabled={!isAdmin}
                  onChange={(e) => update(f.key, e.target.value)}
                  placeholder={f.placeholder}
                />
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {isAdmin && (
        <div className="flex justify-end">
          <Button variant="gradient" onClick={handleSave} disabled={save.isPending || profile.isLoading}>
            {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save profile
          </Button>
        </div>
      )}
    </div>
  );
}
