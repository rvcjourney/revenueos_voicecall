import { Check, Gauge, Languages, Mic, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { SoundWave } from "@/components/shared/SoundWave";
import { usePlatformTab, type PlatformTabId } from "@/lib/platformTab";
import { cn } from "@/lib/utils";

// Visual adaptation of the wireframe's tabbed "Platform" section, populated
// with 4 of the existing feature entries from Landing.tsx's `features` array
// (verbatim title/description) — not new content.
const tabs = [
  {
    id: "cloning",
    label: "Voice cloning",
    icon: Mic,
    title: "Clone any voice, reuse everywhere",
    description:
      "Clone your own voice, a top rep's, or your founder's once — then assign it to any AI agent across every campaign, no re-recording required.",
    panel: "cloning" as const,
  },
  {
    id: "multilingual",
    label: "Hindi & English voice",
    icon: Languages,
    title: "Human-like Hindi & English voice",
    description:
      "Natural, code-switching conversations in Hinglish, Hindi, and English — agents that sound like your best rep, not a robot.",
    panel: "call" as const,
  },
  {
    id: "calling",
    label: "Concurrent calling",
    icon: Gauge,
    title: "Concurrent batch calling",
    description:
      "Dial hundreds of numbers at once. Set your pace, calling windows, and days to match your team's bandwidth and compliance needs.",
    panel: "calling" as const,
  },
  {
    id: "compliance",
    label: "Compliance",
    icon: ShieldCheck,
    title: "Built-in compliance",
    description:
      "Org-level Do Not Call lists, plus automatic enforcement against India's TRAI NCPR registry — compliance without the busywork.",
    panel: "compliance" as const,
  },
] satisfies { id: PlatformTabId; label: string; icon: typeof Mic; title: string; description: string; panel: string }[];

export function PlatformShowcase() {
  const { activeTab, setActiveTab } = usePlatformTab();
  const current = tabs.find((t) => t.id === activeTab) ?? tabs[0];

  return (
    <section id="platform" className="section-pad border-t border-border/60">
      <div className="reveal-on-scroll mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow">Platform</p>
          <h2 className="mt-3 font-heading text-3xl font-semibold sm:text-4xl">The AI platform outbound teams build on</h2>
          <p className="mt-3 text-muted-foreground">
            One place to clone voices, run campaigns, and close deals — in the Hindi and English your customers speak.
          </p>
        </div>

        <div className="mt-10 flex flex-wrap justify-center gap-2">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setActiveTab(t.id)}
              className={cn(
                "flex items-center gap-2 rounded-full border px-5 py-2.5 text-sm font-medium transition-colors",
                activeTab === t.id
                  ? "border-transparent bg-foreground text-background"
                  : "border-border bg-card text-muted-foreground hover:text-foreground"
              )}
            >
              <t.icon className="h-4 w-4" />
              {t.label}
            </button>
          ))}
        </div>

        <div className="glass hover-lift mt-8 grid gap-8 rounded-2xl p-8 lg:grid-cols-[1fr_1.15fr] lg:items-center">
          <div>
            <h3 className="font-heading text-xl font-semibold sm:text-2xl">{current.title}</h3>
            <p className="mt-3 text-sm text-muted-foreground sm:text-base">{current.description}</p>
          </div>
          <PlatformPanel panel={current.panel} />
        </div>
      </div>
    </section>
  );
}

function PlatformPanel({ panel }: { panel: "cloning" | "call" | "calling" | "compliance" }) {
  if (panel === "cloning") {
    return (
      <div className="rounded-xl border border-border bg-card p-5">
        <PanelHeader label="Voice cloning" sub="Founder's voice — 60s sample" status="Cloned" />
        <div className="flex justify-center py-4">
          <SoundWave />
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">Now speaking as:</span>
          <Badge variant="outline">Aniket</Badge>
          <Badge variant="outline">Priya</Badge>
          <Badge variant="outline">+12 more agents</Badge>
        </div>
      </div>
    );
  }

  if (panel === "calling") {
    return (
      <div className="rounded-xl border border-border bg-card p-5">
        <PanelHeader label="Q3 Renewal Campaign" sub="Hundreds of contacts loaded" status="Running" />
        <div className="mt-4 space-y-3 text-sm">
          <Row label="Dialing" value="Concurrent" />
          <Row label="Interested" value="Auto-tagged" accent />
          <Row label="Callback requested" value="Queued" />
        </div>
      </div>
    );
  }

  if (panel === "compliance") {
    return (
      <div className="rounded-xl border border-border bg-card p-5">
        <PanelHeader label="Compliance check" sub="Before every dial" status="Cleared" />
        <div className="mt-4 space-y-3 text-sm">
          <Row label="TRAI NCPR registry" value="Checked automatically" accent />
          <Row label="Org Do Not Call list" value="Checked automatically" accent />
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <PanelHeader label="Aniket — AI Agent" sub="Speaking with Rajesh Sharma" status="Live" />
      <div className="flex justify-center py-4">
        <SoundWave />
      </div>
      <div className="rounded-xl rounded-tl-sm bg-muted p-3 text-sm">
        <p className="mb-1 text-xs font-medium text-muted-foreground">Aniket</p>
        "Sir, main samajh sakta hoon budget ek concern hai — same quality mein hum aapko 30% kam price de sakte hain."
      </div>
    </div>
  );
}

function PanelHeader({ label, sub, status }: { label: string; sub: string; status: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border/60 pb-3">
      <div>
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">{sub}</p>
      </div>
      <Badge variant="success">
        <Check className="h-3 w-3" /> {status}
      </Badge>
    </div>
  );
}

function Row({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("font-medium", accent ? "text-success" : "text-foreground")}>{value}</span>
    </div>
  );
}
