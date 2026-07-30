import { createFileRoute } from "@tanstack/react-router";
import { mockCalls } from "@/lib/mock-data";
import { Button } from "@/components/ui/button";
import { Plus, Upload } from "lucide-react";

export const Route = createFileRoute("/_authed/contacts")({
  head: () => ({ meta: [{ title: "Contacts — MOTMVoice" }] }),
  component: Contacts,
});

function Contacts() {
  const seen = new Set<string>();
  const contacts = mockCalls.filter(c => { if (seen.has(c.phone)) return false; seen.add(c.phone); return true; }).slice(0, 60);
  return (
    <div className="space-y-6 max-w-[1500px]">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Contacts</h1>
          <p className="text-sm text-muted-foreground mt-1">All prospects across your campaigns</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline"><Upload className="h-4 w-4" /> Import CSV</Button>
          <Button className="bg-gradient-primary text-white shadow-glow"><Plus className="h-4 w-4" /> Add Contact</Button>
        </div>
      </div>
      <div className="rounded-xl bg-card border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-muted-foreground bg-surface-2/40">
            <th className="px-4 py-3 font-medium">Name</th>
            <th className="px-4 py-3 font-medium">Phone</th>
            <th className="px-4 py-3 font-medium">Company</th>
            <th className="px-4 py-3 font-medium">Last Campaign</th>
          </tr></thead>
          <tbody>
            {contacts.map(c => (
              <tr key={c.id} className="border-t border-border/60 hover:bg-surface-2/40">
                <td className="px-4 py-2.5 font-medium">{c.contactName}</td>
                <td className="px-4 py-2.5 font-mono text-xs">{c.phone}</td>
                <td className="px-4 py-2.5">{c.company}</td>
                <td className="px-4 py-2.5 text-xs text-muted-foreground">{c.campaignName}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
