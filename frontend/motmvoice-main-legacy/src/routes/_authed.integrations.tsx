import { createFileRoute } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Plug, Webhook } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_authed/integrations")({
  head: () => ({ meta: [{ title: "Integrations — MOTMVoice" }] }),
  component: Integrations,
});

const apps = [
  { name: "Salesforce", desc: "Sync leads & contacts", connected: true },
  { name: "HubSpot", desc: "Push call data to CRM", connected: false },
  { name: "Zoho CRM", desc: "Bidirectional sync", connected: false },
  { name: "Google Sheets", desc: "Auto-export interested leads", connected: true },
  { name: "Slack", desc: "Real-time call notifications", connected: true },
  { name: "Zapier", desc: "5,000+ app integrations", connected: false },
];

function Integrations() {
  return (
    <div className="space-y-6 max-w-[1500px]">
      <div>
        <h1 className="text-2xl font-bold">Integrations</h1>
        <p className="text-sm text-muted-foreground mt-1">Connect MOTMVoice to your existing tools</p>
      </div>

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {apps.map(a => (
          <div key={a.name} className="rounded-xl bg-card border border-border p-5">
            <div className="flex items-start justify-between mb-3">
              <div className="h-12 w-12 rounded-lg bg-surface-3 grid place-items-center text-primary"><Plug className="h-6 w-6" /></div>
              {a.connected && <span className="text-[10px] px-2 py-0.5 rounded-full bg-success/15 text-success border border-success/30">CONNECTED</span>}
            </div>
            <h3 className="font-semibold">{a.name}</h3>
            <p className="text-xs text-muted-foreground mt-1">{a.desc}</p>
            <Button
              variant={a.connected ? "outline" : "default"}
              size="sm"
              className={`mt-4 w-full ${!a.connected ? "bg-gradient-primary text-white" : ""}`}
              onClick={() => toast.success(`${a.name} ${a.connected ? "disconnected" : "connected"}`)}
            >
              {a.connected ? "Disconnect" : "Connect"}
            </Button>
          </div>
        ))}
      </div>

      <div className="rounded-xl bg-card border border-border p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="font-semibold flex items-center gap-2"><Webhook className="h-4 w-4" /> Webhooks</h3>
            <p className="text-xs text-muted-foreground mt-1">Fire HTTP requests on call events</p>
          </div>
          <Button size="sm" variant="outline">+ Add Webhook</Button>
        </div>
        <div className="rounded-lg bg-surface-2 border border-border p-4 font-mono text-xs">
          <div className="flex items-center justify-between">
            <span>https://yourapp.com/api/motm-webhook</span>
            <span className="text-success">● Active</span>
          </div>
        </div>
      </div>
    </div>
  );
}
