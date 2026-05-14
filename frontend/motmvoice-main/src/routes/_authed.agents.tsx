import { createFileRoute } from "@tanstack/react-router";
import { promptTemplates, voices } from "@/lib/mock-data";
import { Button } from "@/components/ui/button";
import { Plus, Bot, Edit, Copy } from "lucide-react";

export const Route = createFileRoute("/_authed/agents")({
  head: () => ({ meta: [{ title: "AI Agents — MOTMVoice" }] }),
  component: Agents,
});

function Agents() {
  return (
    <div className="space-y-6 max-w-[1500px]">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">AI Agents</h1>
          <p className="text-sm text-muted-foreground mt-1">Reusable agent templates and system prompts</p>
        </div>
        <Button className="bg-gradient-primary text-white shadow-glow"><Plus className="h-4 w-4" /> Create Agent</Button>
      </div>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {promptTemplates.map((t, i) => {
          const v = voices[i % voices.length];
          return (
            <div key={t.id} className="rounded-xl bg-card border border-border p-5 hover:border-primary/40 transition-colors">
              <div className="flex items-start justify-between mb-3">
                <div className="h-12 w-12 rounded-lg bg-gradient-primary grid place-items-center text-white"><Bot className="h-6 w-6" /></div>
                <span className="text-xs px-2 py-0.5 rounded bg-surface-3 text-muted-foreground">{t.lang}</span>
              </div>
              <h3 className="font-semibold">{t.name}</h3>
              <p className="text-xs text-muted-foreground mt-1">{t.desc}</p>
              <div className="mt-4 text-xs text-muted-foreground">Voice: <span className="text-foreground">{v.name}</span></div>
              <div className="mt-1 text-xs text-muted-foreground">Last edited: 2 days ago</div>
              <div className="mt-4 flex gap-2">
                <Button variant="outline" size="sm" className="flex-1"><Edit className="h-3 w-3" /> Edit</Button>
                <Button variant="ghost" size="sm"><Copy className="h-3 w-3" /></Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
