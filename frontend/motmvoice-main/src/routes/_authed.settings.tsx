import { createFileRoute } from "@tanstack/react-router";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { Progress } from "@/components/ui/progress";
import { Plus, Copy } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_authed/settings")({
  head: () => ({ meta: [{ title: "Settings — MOTMVoice" }] }),
  component: SettingsPage,
});

function SettingsPage() {
  const { user } = useAuth();
  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">Manage your account and team</p>
      </div>
      <Tabs defaultValue="profile">
        <TabsList className="bg-card border border-border">
          {["profile","team","billing","api","phone","notif"].map(t => (
            <TabsTrigger key={t} value={t} className="capitalize">{t === "api" ? "API Keys" : t === "phone" ? "Phone Numbers" : t === "notif" ? "Notifications" : t}</TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="profile" className="rounded-xl bg-card border border-border p-6 mt-4 space-y-4 max-w-xl">
          <div className="space-y-1.5"><Label>Full name</Label><Input defaultValue={user?.full_name} /></div>
          <div className="space-y-1.5"><Label>Email</Label><Input defaultValue={user?.email} /></div>
          <div className="space-y-1.5"><Label>Company</Label><Input defaultValue={user?.org_name} /></div>
          <Button className="bg-gradient-primary text-white" onClick={() => toast.success("Saved")}>Save changes</Button>
        </TabsContent>

        <TabsContent value="team" className="rounded-xl bg-card border border-border p-6 mt-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">Team Members</h3>
            <Button size="sm" className="bg-gradient-primary text-white"><Plus className="h-4 w-4" /> Invite</Button>
          </div>
          {[user?.full_name ?? "You","Priya Iyer","Amit Patel"].map((n,i) => (
            <div key={n} className="flex items-center gap-3 p-3 rounded-lg bg-surface-2 border border-border">
              <div className="h-9 w-9 rounded-full bg-gradient-primary grid place-items-center text-white text-sm font-semibold">{n[0]}</div>
              <div className="flex-1"><div className="text-sm font-medium">{n}</div><div className="text-xs text-muted-foreground">{i === 0 ? user?.email : `${n.split(' ')[0].toLowerCase()}@motmvoice.ai`}</div></div>
              <span className="text-xs px-2 py-1 rounded bg-primary/15 text-primary">{i === 0 ? "Admin" : "Sales Rep"}</span>
            </div>
          ))}
        </TabsContent>

        <TabsContent value="billing" className="rounded-xl bg-card border border-border p-6 mt-4 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm text-muted-foreground">Current Plan</div>
              <div className="text-2xl font-bold mt-1">Growth — ₹29,999/mo</div>
            </div>
            <Button variant="outline">Upgrade</Button>
          </div>
          <div>
            <div className="flex items-center justify-between text-sm mb-2"><span>Calls used this month</span><span className="font-mono">42,180 / 75,000</span></div>
            <Progress value={56} className="h-2" />
          </div>
        </TabsContent>

        <TabsContent value="api" className="rounded-xl bg-card border border-border p-6 mt-4 space-y-3">
          <h3 className="font-semibold">API Keys</h3>
          <div className="flex items-center gap-2 p-3 rounded-lg bg-surface-2 border border-border">
            <code className="font-mono text-xs flex-1">sk_live_motm_a1b2c3d4e5f6…</code>
            <Button size="sm" variant="ghost" onClick={() => toast.success("Copied")}><Copy className="h-3 w-3" /></Button>
          </div>
          <Button size="sm" className="bg-gradient-primary text-white">Generate New Key</Button>
        </TabsContent>

        <TabsContent value="phone" className="rounded-xl bg-card border border-border p-6 mt-4 space-y-3">
          <h3 className="font-semibold">SIP Phone Numbers</h3>
          {["+91 80691 12345","+91 80691 67890"].map(p => (
            <div key={p} className="flex items-center justify-between p-3 rounded-lg bg-surface-2 border border-border">
              <div className="font-mono text-sm">{p}</div>
              <span className="text-xs text-success">● Active</span>
            </div>
          ))}
        </TabsContent>

        <TabsContent value="notif" className="rounded-xl bg-card border border-border p-6 mt-4 space-y-3">
          <h3 className="font-semibold">Notification Preferences</h3>
          <p className="text-sm text-muted-foreground">Email me when an interested lead comes in, when a campaign completes, or when call quota is 80% used.</p>
        </TabsContent>
      </Tabs>
    </div>
  );
}
