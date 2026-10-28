import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Bell, Loader2, Phone, User as UserIcon, Users as UsersIcon, Webhook, type LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { useMyTrunks } from "@/lib/hooks";
import { adminApi, authApi, apiErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

const tabs = [
  { value: "profile", label: "Profile", icon: UserIcon },
  { value: "team", label: "Team", icon: UsersIcon },
  { value: "phone-numbers", label: "Phone Numbers", icon: Phone },
  { value: "integrations", label: "Integrations", icon: Webhook },
  { value: "notifications", label: "Notifications", icon: Bell },
];

export default function Settings() {
  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Manage your account, team, and preferences" />

      <Tabs defaultValue="profile" orientation="vertical" className="flex flex-col gap-6 lg:flex-row">
        <TabsList className="h-fit flex-col items-stretch gap-1 bg-transparent p-0 lg:w-56">
          {tabs.map((t) => (
            <TabsTrigger
              key={t.value}
              value={t.value}
              className={cn("justify-start gap-2 rounded-lg px-3 py-2 data-[state=active]:bg-card data-[state=active]:shadow-none")}
            >
              <t.icon className="h-4 w-4" /> {t.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <div className="flex-1">
          <TabsContent value="profile"><ProfileTab /></TabsContent>
          <TabsContent value="team"><TeamTab /></TabsContent>
          <TabsContent value="phone-numbers"><PhoneNumbersTab /></TabsContent>
          <TabsContent value="integrations"><IntegrationsTab /></TabsContent>
          <TabsContent value="notifications"><ComingSoon icon={Bell} title="Notification preferences" /></TabsContent>
        </div>
      </Tabs>
    </div>
  );
}

function ProfileTab() {
  const { user, refreshUser } = useAuth();
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (password && password.length < 6) {
      toast.error("Password must be at least 6 characters");
      return;
    }
    setSaving(true);
    try {
      await authApi.updateProfile({ full_name: fullName, password: password || undefined });
      await refreshUser();
      toast.success("Profile updated");
      setPassword("");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't update profile"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardContent className="max-w-md space-y-5 pt-6">
        <div>
          <p className="font-medium">Profile</p>
          <p className="text-sm text-muted-foreground">Your personal information</p>
        </div>
        <div className="space-y-1.5">
          <Label>Full name</Label>
          <Input value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label>Email address</Label>
          <Input value={user?.email} disabled />
        </div>
        <div className="space-y-1.5">
          <Label>Organization</Label>
          <Input value={user?.org_name} disabled />
        </div>
        <div className="space-y-1.5">
          <Label>New password</Label>
          <Input type="password" placeholder="Leave blank to keep your current password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        <Button variant="gradient" onClick={handleSave} disabled={saving}>
          {saving && <Loader2 className="h-4 w-4 animate-spin" />}
          Save changes
        </Button>
      </CardContent>
    </Card>
  );
}

function TeamTab() {
  const { user, isAdmin } = useAuth();
  return (
    <Card>
      <CardContent className="max-w-md space-y-4 pt-6">
        <div>
          <p className="font-medium">Team</p>
          <p className="text-sm text-muted-foreground">You're part of {user?.org_name}</p>
        </div>
        {isAdmin ? (
          <Button variant="outline" asChild>
            <Link to="/admin/team">Manage team members</Link>
          </Button>
        ) : (
          <p className="text-sm text-muted-foreground">
            Ask your organization admin to add or remove team members, or to grant you access to AI agents.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function PhoneNumbersTab() {
  const { isAdmin } = useAuth();
  const trunks = useMyTrunks();

  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-medium">Phone Numbers</p>
            <p className="text-sm text-muted-foreground">Numbers your account can call from</p>
          </div>
          {isAdmin && (
            <Button variant="outline" size="sm" asChild>
              <Link to="/admin/phone-numbers">Manage all numbers</Link>
            </Button>
          )}
        </div>
        {trunks.isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : trunks.data && trunks.data.length > 0 ? (
          <div className="space-y-2">
            {trunks.data.map((t) => (
              <div key={t.id} className="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-sm">
                <span className="font-mono">{t.caller_id}</span>
                <span className="text-xs text-muted-foreground">{t.name}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No phone numbers assigned to your account yet.</p>
        )}
      </CardContent>
    </Card>
  );
}

function IntegrationsTab() {
  const { isAdmin } = useAuth();
  const [url, setUrl] = useState("");
  const [hasSecret, setHasSecret] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAdmin) return;
    adminApi.webhook()
      .then(({ data }) => { setUrl(data.url ?? ""); setHasSecret(data.has_secret); })
      .catch(() => toast.error("Couldn't load webhook settings"))
      .finally(() => setLoading(false));
  }, [isAdmin]);

  if (!isAdmin) {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-muted-foreground">
          Ask your organization admin to set up integrations.
        </CardContent>
      </Card>
    );
  }

  async function save(regenerate = false) {
    setBusy(true);
    try {
      const { data } = await adminApi.setWebhook({ url: url.trim() || null, regenerate_secret: regenerate });
      setHasSecret(data.has_secret);
      setSecret(data.secret);
      toast.success(data.url ? "Webhook saved" : "Webhook turned off");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't save webhook"));
    } finally {
      setBusy(false);
    }
  }

  async function sendTest() {
    setBusy(true);
    try {
      const { data } = await adminApi.testWebhook();
      (data.ok ? toast.success : toast.error)(data.detail);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Test failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardContent className="max-w-xl space-y-5 pt-6">
        <div>
          <p className="font-medium">Webhook</p>
          <p className="text-sm text-muted-foreground">
            After every call we send the outcome, summary, extracted data and transcript to this URL. Connect it to
            Zapier, Make or your CRM.
          </p>
        </div>
        {loading ? (
          <Skeleton className="h-10 w-full" />
        ) : (
          <>
            <div className="space-y-1.5">
              <Label>Webhook URL (https)</Label>
              <Input placeholder="https://hooks.zapier.com/..." value={url} onChange={(e) => setUrl(e.target.value)} />
              <p className="text-xs text-muted-foreground">Leave blank and save to turn it off.</p>
            </div>
            {secret && (
              <div className="space-y-1.5 rounded-lg border border-border p-3">
                <Label>Signing secret — copy it now, it won't be shown again</Label>
                <p className="break-all font-mono text-xs">{secret}</p>
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button variant="gradient" onClick={() => save(false)} disabled={busy}>
                {busy && <Loader2 className="h-4 w-4 animate-spin" />} Save
              </Button>
              {hasSecret && (
                <>
                  <Button variant="outline" onClick={sendTest} disabled={busy}>Send test</Button>
                  <Button variant="outline" onClick={() => save(true)} disabled={busy}>New secret</Button>
                </>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ComingSoon({ icon, title }: { icon: LucideIcon; title: string }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <EmptyState icon={icon} title={`${title} — coming soon`} description="This section isn't connected to a backend yet." />
      </CardContent>
    </Card>
  );
}
