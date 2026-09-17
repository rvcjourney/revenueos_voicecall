import { Link } from "react-router-dom";
import { AlertTriangle, Building2, Calendar, CheckCircle2, FileSpreadsheet, Phone, Plus, Sparkles, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { CampaignStatusBadge } from "@/components/shared/StatusBadge";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { useCampaigns, useCompanyProfile } from "@/lib/hooks";
import { formatDate } from "@/lib/utils";

const HOW_IT_WORKS = [
  { icon: Building2, title: "1. Company Profile", text: "Tell the AI once who you are and what you offer." },
  { icon: FileSpreadsheet, title: "2. Upload contacts", text: "CSV with name, designation, company, website, location…" },
  { icon: Wand2, title: "3. AI personalises", text: "Before each call, a prompt is written just for that person." },
  { icon: Phone, title: "4. Calls go out", text: "The agent greets them by name and talks about their business." },
];

export default function PrimeCalling() {
  const profile = useCompanyProfile();
  const campaigns = useCampaigns({ is_prime: true });
  const profileReady = profile.data?.is_complete ?? false;

  return (
    <div className="space-y-6">
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-primary" /> Prime Calling
          </span>
        }
        description="Campaigns where every call is personalised by AI for the person being called."
        actions={
          <>
            <Button variant="outline" asChild>
              <Link to="/prime-calling/company">
                <Building2 className="h-4 w-4" /> Company Profile
              </Link>
            </Button>
            <Button variant="gradient" asChild>
              <Link to="/prime-calling/new">
                <Plus className="h-4 w-4" /> New Prime Campaign
              </Link>
            </Button>
          </>
        }
      />

      {profile.isSuccess &&
        (profileReady ? (
          <div className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
            <span>
              Company Profile ready for <span className="font-medium">{profile.data.company_name}</span>.
            </span>
          </div>
        ) : (
          <div className="flex flex-col gap-3 rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
            <span className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
              Start here: fill in your Company Profile so the AI knows what you're selling.
            </span>
            <Button size="sm" variant="outline" asChild>
              <Link to="/prime-calling/company">Set up profile</Link>
            </Button>
          </div>
        ))}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {HOW_IT_WORKS.map(({ icon: Icon, title, text }) => (
          <Card key={title}>
            <CardContent className="space-y-2 pt-5">
              <Icon className="h-5 w-5 text-primary" />
              <p className="text-sm font-semibold">{title}</p>
              <p className="text-xs text-muted-foreground">{text}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <section className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Prime Campaigns</p>
        {campaigns.isError ? (
          <ErrorBanner error={campaigns.error} onRetry={() => campaigns.refetch()} />
        ) : campaigns.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-32 w-full" />
            ))}
          </div>
        ) : campaigns.data && campaigns.data.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {campaigns.data.map((c) => {
              const pct = c.total_contacts ? Math.round((c.completed_calls / c.total_contacts) * 100) : 0;
              return (
                <Link key={c.id} to={`/campaigns/${c.id}`} className="group block h-full">
                  <div className="flex h-full flex-col gap-3 rounded-2xl border border-border bg-card p-5 shadow-[var(--shadow-card)] transition-all duration-200 group-hover:-translate-y-1 group-hover:shadow-[var(--shadow-elevated)]">
                    <div className="flex items-start justify-between gap-3">
                      <p className="font-heading text-base font-semibold leading-snug">{c.name}</p>
                      <CampaignStatusBadge status={c.status} className="shrink-0" />
                    </div>
                    <div className="space-y-1.5">
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>
                          {c.completed_calls} / {c.total_contacts} calls
                        </span>
                        <span>{pct}%</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                        <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                    <div className="mt-auto flex items-center justify-between text-xs text-muted-foreground">
                      <span>{c.interested_count} interested</span>
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {formatDate(c.created_at)}
                      </span>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        ) : (
          <EmptyState
            icon={Sparkles}
            title="No Prime campaigns yet"
            description="Upload a contact list and let the AI personalise every call."
            action={
              <Button variant="gradient" asChild>
                <Link to="/prime-calling/new">New Prime Campaign</Link>
              </Button>
            }
          />
        )}
      </section>
    </div>
  );
}
