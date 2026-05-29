import { createFileRoute, Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { SoundWave } from "@/components/marketing/SoundWave";
import { Mic, PhoneCall, Upload, Settings2, Rocket, Download, BarChart3, Zap, Languages, FileSpreadsheet, ShieldCheck, Plug, Check } from "lucide-react";
import { LogoMark } from "@/components/Logo";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "MOTMVoice — Automate 1500+ AI Sales Calls Daily" },
      { name: "description", content: "Hinglish, English & 20+ languages. Human-like AI voice agents. Real-time analytics. Built for high-volume B2B outbound." },
      { property: "og:title", content: "MOTMVoice — AI Voice Sales Call Automation" },
      { property: "og:description", content: "Automate outbound calling at scale with AI voice agents that actually convert." },
    ],
  }),
  component: Landing,
});

function Nav() {
  return (
    <nav className="sticky top-0 z-50 glass border-b border-border/40">
      <div className="mx-auto max-w-7xl px-6 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div style={{ filter: "drop-shadow(0 0 8px oklch(0.55 0.24 278 / 0.55))" }}>
            <LogoMark size={32} />
          </div>
          <span
            className="font-bold text-lg tracking-tight"
            style={{
              background: "linear-gradient(135deg, #fff 30%, oklch(0.78 0.18 268))",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}
          >
            MOTM<span style={{ fontWeight: 300 }}>Voice</span>
          </span>
        </Link>
        <div className="hidden md:flex items-center gap-8 text-sm text-muted-foreground">
          <a href="#features" className="hover:text-foreground transition-colors">Features</a>
          <a href="#how" className="hover:text-foreground transition-colors">How it works</a>
          <a href="#pricing" className="hover:text-foreground transition-colors">Pricing</a>
          <a href="#" className="hover:text-foreground transition-colors">Docs</a>
        </div>
        <div className="flex items-center gap-3">
          <Link to="/login"><Button variant="ghost" size="sm">Login</Button></Link>
          <Link to="/signup"><Button size="sm" className="bg-gradient-primary text-white shadow-glow hover:opacity-90">Get Started</Button></Link>
        </div>
      </div>
    </nav>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div className="absolute inset-0 bg-mesh opacity-70" />
      <div className="relative mx-auto max-w-7xl px-6 pt-20 pb-24 grid lg:grid-cols-2 gap-12 items-center">
        <div className="fade-up">
          <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full glass text-xs font-medium text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
            Live: 1,247 calls happening right now
          </span>
          <h1 className="mt-6 text-5xl md:text-6xl font-bold tracking-tight leading-[1.05]">
            Automate <span className="text-gradient">1500+ Sales Calls</span> Daily with AI Voice Agents
          </h1>
          <p className="mt-6 text-lg text-muted-foreground max-w-xl">
            Hinglish, English & 20+ languages. Human-like conversations.
            Real-time analytics. Built for high-volume B2B outbound teams.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/signup">
              <Button size="lg" className="bg-gradient-primary text-white shadow-glow hover:opacity-90">
                <Rocket className="h-4 w-4" /> Start Free Trial
              </Button>
            </Link>
            <Button size="lg" variant="outline" className="border-border">
              <PhoneCall className="h-4 w-4" /> Watch Demo
            </Button>
          </div>
        </div>
        <div className="relative fade-up" style={{ animationDelay: "120ms" }}>
          <div className="relative rounded-2xl glass p-8 shadow-card">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-gradient-primary grid place-items-center">
                  <Mic className="h-5 w-5 text-white" />
                </div>
                <div>
                  <div className="font-semibold text-sm">Aniket — AI Agent</div>
                  <div className="text-xs text-muted-foreground">Speaking with Rajesh Sharma</div>
                </div>
              </div>
              <span className="font-mono text-xs text-success">● LIVE 02:14</span>
            </div>
            <SoundWave bars={28} />
            <div className="mt-6 space-y-3 text-sm">
              <div className="rounded-lg bg-surface-3/60 p-3">
                <div className="text-xs text-muted-foreground mb-1">Aniket</div>
                <div>"Sir hum same quality 30% kam price mein de sakte hain. Demo schedule kar du?"</div>
              </div>
              <div className="rounded-lg bg-primary/15 border border-primary/20 p-3">
                <div className="text-xs text-primary mb-1">Rajesh</div>
                <div>"Theek hai, agle hafte try karte hain."</div>
              </div>
            </div>
          </div>
          <div className="absolute -bottom-4 -right-4 px-3 py-2 rounded-lg bg-success/15 border border-success/30 text-xs font-medium text-success backdrop-blur">
            ✓ Marked as Hot Lead
          </div>
        </div>
      </div>
    </section>
  );
}

const stats = [
  { v: "10,000+", l: "Calls Made Daily" },
  { v: "92%", l: "Pickup Rate" },
  { v: "<500ms", l: "Voice Latency" },
  { v: "24/7", l: "Uptime" },
];

function Stats() {
  return (
    <section className="border-y border-border/50 bg-surface-2/40">
      <div className="mx-auto max-w-7xl px-6 py-10 grid grid-cols-2 md:grid-cols-4 gap-6">
        {stats.map((s) => (
          <div key={s.l} className="text-center">
            <div className="text-3xl font-bold font-mono text-gradient">{s.v}</div>
            <div className="text-xs text-muted-foreground mt-1 uppercase tracking-wider">{s.l}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

const features = [
  { icon: Languages, title: "AI Voice Agents", desc: "Hinglish + 20 languages. Voices indistinguishable from humans." },
  { icon: FileSpreadsheet, title: "CSV/Excel Bulk Upload", desc: "Drag & drop thousands of contacts. Smart column mapping & validation." },
  { icon: Settings2, title: "Custom System Prompts", desc: "Per-campaign agent personas. AI-assisted prompt improvement." },
  { icon: BarChart3, title: "Real-Time Analytics", desc: "Live call dashboards, outcome breakdowns, conversion funnels." },
  { icon: Download, title: "Interested Lead Export", desc: "One-click Excel export of qualified leads with tags & notes." },
  { icon: Plug, title: "CRM Integration Ready", desc: "Salesforce, HubSpot, Zoho, Slack, webhooks & Zapier." },
];

function Features() {
  return (
    <section id="features" className="mx-auto max-w-7xl px-6 py-24">
      <div className="text-center max-w-2xl mx-auto">
        <h2 className="text-4xl font-bold tracking-tight">Everything your sales team needs</h2>
        <p className="mt-4 text-muted-foreground">A complete control plane for high-volume AI outbound calling.</p>
      </div>
      <div className="mt-14 grid md:grid-cols-2 lg:grid-cols-3 gap-5">
        {features.map((f) => (
          <div key={f.title} className="group rounded-xl bg-surface-2 border border-border p-6 hover:border-primary/40 transition-colors">
            <div className="h-11 w-11 rounded-lg bg-primary/15 grid place-items-center text-primary mb-4 group-hover:shadow-glow transition-shadow">
              <f.icon className="h-5 w-5" />
            </div>
            <h3 className="font-semibold">{f.title}</h3>
            <p className="mt-2 text-sm text-muted-foreground">{f.desc}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

const steps = [
  { icon: Upload, title: "Upload Contacts", desc: "Drag a CSV with thousands of leads." },
  { icon: Settings2, title: "Configure Agent", desc: "Pick a voice & write a system prompt." },
  { icon: Rocket, title: "Launch Campaign", desc: "Calls dial out at your chosen pace." },
  { icon: Download, title: "Export Leads", desc: "Download interested prospects to Excel." },
];

function HowItWorks() {
  return (
    <section id="how" className="mx-auto max-w-7xl px-6 py-24 border-t border-border/50">
      <div className="text-center max-w-2xl mx-auto">
        <h2 className="text-4xl font-bold tracking-tight">From CSV to closed deals in 4 steps</h2>
      </div>
      <div className="mt-14 grid md:grid-cols-4 gap-6 relative">
        {steps.map((s, i) => (
          <div key={s.title} className="relative">
            <div className="rounded-xl bg-surface-2 border border-border p-6 h-full">
              <div className="flex items-center justify-between mb-4">
                <div className="h-10 w-10 rounded-lg bg-gradient-primary grid place-items-center text-white">
                  <s.icon className="h-5 w-5" />
                </div>
                <span className="font-mono text-xs text-muted-foreground">0{i + 1}</span>
              </div>
              <h3 className="font-semibold">{s.title}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{s.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

const testimonials = [
  { name: "Rajesh K.", role: "Sales Head, Baba Valves", quote: "MOTMVoice replaced 8 of my callers. We're booking 3x more demos and the Hinglish quality is uncanny." },
  { name: "Priya M.", role: "Founder, ChemTech", quote: "Set up a campaign in 10 minutes. By morning we had 47 qualified leads sitting in Excel. Insane." },
  { name: "Amit S.", role: "VP Sales, Hindustan Pumps", quote: "The transcript & sentiment analysis alone is worth it. Real visibility into every conversation." },
];

function Testimonials() {
  return (
    <section className="mx-auto max-w-7xl px-6 py-24">
      <div className="text-center max-w-2xl mx-auto">
        <h2 className="text-4xl font-bold tracking-tight">Loved by sales teams across India</h2>
      </div>
      <div className="mt-14 grid md:grid-cols-3 gap-5">
        {testimonials.map((t) => (
          <div key={t.name} className="rounded-xl glass p-6">
            <p className="text-sm leading-relaxed">"{t.quote}"</p>
            <div className="mt-6 flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-gradient-primary grid place-items-center text-white font-semibold text-sm">
                {t.name[0]}
              </div>
              <div>
                <div className="text-sm font-semibold">{t.name}</div>
                <div className="text-xs text-muted-foreground">{t.role}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

const tiers = [
  { name: "Starter", price: "₹9,999", period: "/mo", desc: "For small teams getting started", features: ["500 calls/day", "1 AI agent", "Basic analytics", "Email support"], cta: "Start Free" },
  { name: "Growth", price: "₹29,999", period: "/mo", desc: "Most popular for growing sales teams", features: ["2,500 calls/day", "5 AI agents", "Advanced analytics", "CRM integrations", "Priority support"], cta: "Start Free", featured: true },
  { name: "Enterprise", price: "Custom", period: "", desc: "Unlimited scale, dedicated infra", features: ["Unlimited calls", "Custom voices", "On-prem option", "SLA & dedicated CSM"], cta: "Contact Sales" },
];

function Pricing() {
  return (
    <section id="pricing" className="mx-auto max-w-7xl px-6 py-24 border-t border-border/50">
      <div className="text-center max-w-2xl mx-auto">
        <h2 className="text-4xl font-bold tracking-tight">Simple, predictable pricing</h2>
        <p className="mt-4 text-muted-foreground">No per-minute charges. No surprises.</p>
      </div>
      <div className="mt-14 grid md:grid-cols-3 gap-5">
        {tiers.map((t) => (
          <div key={t.name} className={`rounded-xl p-6 border ${t.featured ? "bg-surface-2 border-primary/40 shadow-glow gradient-border" : "bg-surface-2 border-border"}`}>
            {t.featured && <div className="text-xs font-semibold text-primary uppercase tracking-wider mb-2">Most Popular</div>}
            <h3 className="text-xl font-bold">{t.name}</h3>
            <p className="text-sm text-muted-foreground mt-1">{t.desc}</p>
            <div className="mt-6 flex items-baseline gap-1">
              <span className="text-4xl font-bold font-mono">{t.price}</span>
              <span className="text-muted-foreground">{t.period}</span>
            </div>
            <ul className="mt-6 space-y-3 text-sm">
              {t.features.map((f) => (
                <li key={f} className="flex items-center gap-2">
                  <Check className="h-4 w-4 text-success shrink-0" /> {f}
                </li>
              ))}
            </ul>
            <Link to="/signup" className="block mt-8">
              <Button className={`w-full ${t.featured ? "bg-gradient-primary text-white shadow-glow" : ""}`} variant={t.featured ? "default" : "outline"}>
                {t.cta}
              </Button>
            </Link>
          </div>
        ))}
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-border/50 mt-12">
      <div className="mx-auto max-w-7xl px-6 py-12 grid md:grid-cols-4 gap-8 text-sm">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <div style={{ filter: "drop-shadow(0 0 6px oklch(0.55 0.24 278 / 0.45))" }}>
              <LogoMark size={28} />
            </div>
            <span
              className="font-bold"
              style={{
                background: "linear-gradient(135deg, #fff 30%, oklch(0.78 0.18 268))",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}
            >
              MOTM<span style={{ fontWeight: 300 }}>Voice</span>
            </span>
          </div>
          <p className="text-muted-foreground text-xs">Voice that converts.</p>
        </div>
        {[
          { h: "Product", l: ["Features", "Pricing", "Integrations", "API"] },
          { h: "Company", l: ["About", "Blog", "Careers", "Contact"] },
          { h: "Legal", l: ["Privacy", "Terms", "Security", "DPDP Act"] },
        ].map((g) => (
          <div key={g.h}>
            <div className="font-semibold mb-3">{g.h}</div>
            <ul className="space-y-2 text-muted-foreground">
              {g.l.map((x) => <li key={x}><a href="#" className="hover:text-foreground">{x}</a></li>)}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-border/50 py-5 text-center text-xs text-muted-foreground">
        © 2026 MOTMVoice. All rights reserved.
      </div>
    </footer>
  );
}

function Landing() {
  return (
    <div className="min-h-screen">
      <Nav />
      <Hero />
      <Stats />
      <Features />
      <HowItWorks />
      <Testimonials />
      <Pricing />
      <Footer />
    </div>
  );
}
