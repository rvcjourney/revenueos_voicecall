import { useRef, useState } from "react";
import {
  Briefcase,
  Building2,
  Download,
  FileText,
  Gauge,
  Languages,
  LineChart,
  Menu,
  Mic,
  Rocket,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Upload,
  X,
  Zap,
} from "lucide-react";
import { Logo } from "@/components/shared/Logo";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { Button } from "@/components/ui/button";
import { LOGIN_URL, SIGNUP_URL } from "@/lib/env";
import { usePlatformTab, type PlatformTabId } from "@/lib/platformTab";
import { cn } from "@/lib/utils";

// Hover-expand panel content, mirrored verbatim from the sections it
// previews (PlatformShowcase's tabs, PlatformPillars' pillars, HowItWorks'
// steps, Pricing's plan capacity lines) — same existing copy, just surfaced
// a second time as nav previews (like Sarvam's mega menus), not new content.
// `tabId` (Platform items only) also selects the matching tab in
// PlatformShowcase so clicking "Multilingual voice" lands on that tab, not
// whichever one is active by default.
interface NavMenuItem {
  icon: typeof Mic;
  label: string;
  description: string;
  tabId?: PlatformTabId;
}

const platformMenu: NavMenuItem[] = [
  { icon: Mic, label: "Voice cloning", description: "Clone any voice, reuse everywhere", tabId: "cloning" },
  { icon: Languages, label: "Multilingual voice", description: "Human-like, code-switching conversations", tabId: "multilingual" },
  { icon: Gauge, label: "Concurrent calling", description: "Dial hundreds of numbers at once", tabId: "calling" },
  { icon: ShieldCheck, label: "Compliance", description: "Org-level DNC lists + TRAI NCPR checks", tabId: "compliance" },
];

const featuresMenu: NavMenuItem[] = [
  { icon: Mic, label: "Voices", description: "Multilingual voice cloning for every agent" },
  { icon: LineChart, label: "Campaigns", description: "Bulk import, concurrent calling, live dashboard" },
  { icon: FileText, label: "Insights", description: "Transcripts, AI summaries, segmented exports" },
];

const howItWorksMenu: NavMenuItem[] = [
  { icon: Upload, label: "01 · Upload Contacts", description: "Drag in a CSV or Excel file with thousands of leads" },
  { icon: Mic, label: "02 · Clone Your Voice", description: "Record 60 seconds, clone it once, reuse it anywhere" },
  { icon: SlidersHorizontal, label: "03 · Configure Agent", description: "Pick a voice, a language, and a system prompt" },
  { icon: Rocket, label: "04 · Launch Campaign", description: "Calls go out concurrently, at your pace" },
  { icon: Download, label: "05 · Export Leads", description: "Download results the moment they're ready" },
];

const pricingMenu: NavMenuItem[] = [
  { icon: Sparkles, label: "Starter", description: "500 AI call-minutes every month" },
  { icon: Zap, label: "Professional", description: "1,600 AI call-minutes every month" },
  { icon: Building2, label: "Enterprise", description: "3,200 AI call-minutes every month" },
  { icon: Briefcase, label: "Business", description: "Custom call-minute volume" },
];

const links = [
  { href: "#platform", label: "Platform", menu: platformMenu },
  { href: "#features", label: "Features", menu: featuresMenu },
  { href: "#how-it-works", label: "How it works", menu: howItWorksMenu },
  { href: "#pricing", label: "Pricing", menu: pricingMenu },
];

export function Nav() {
  const [open, setOpen] = useState(false);
  const [activeMenu, setActiveMenu] = useState<string | null>(null);
  const closeTimer = useRef<number | undefined>(undefined);
  const { setActiveTab } = usePlatformTab();

  const openMenu = (href: string) => {
    window.clearTimeout(closeTimer.current);
    setActiveMenu(href);
  };
  const scheduleClose = () => {
    window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => setActiveMenu(null), 180);
  };

  const active = links.find((l) => l.href === activeMenu);

  return (
    <header className="sticky top-3 z-40 mx-auto max-w-6xl px-4 sm:top-4 sm:px-6 lg:px-8" onMouseLeave={scheduleClose}>
      <div className="glass flex h-20 items-center justify-between rounded-full border border-border px-5 shadow-[var(--shadow-elevated)] sm:px-6">
        <a href="#top">
          <Logo className="text-xl" iconClassName="h-10" />
        </a>

        <nav className="hidden items-center gap-8 md:flex">
          {links.map((l) => (
            <a
              key={l.href}
              href={l.href}
              onMouseEnter={() => openMenu(l.href)}
              className={cn(
                "text-sm font-medium text-muted-foreground transition-colors hover:text-foreground",
                activeMenu === l.href && "text-foreground"
              )}
            >
              {l.label}
            </a>
          ))}
        </nav>

        <div className="hidden items-center gap-2 md:flex">
          <ThemeToggle />
          <Button variant="outline" size="sm" className="rounded-full" asChild>
            <a href={LOGIN_URL}>Log in</a>
          </Button>
          <Button variant="gradient" size="sm" className="rounded-full" asChild>
            <a href={SIGNUP_URL}>Get started</a>
          </Button>
        </div>

        <button className="md:hidden" onClick={() => setOpen((v) => !v)} aria-label="Toggle menu">
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {/* Hover mega-menu — every top-level nav item expands into a preview
          of its section's real content. */}
      <div
        onMouseEnter={() => active?.menu && openMenu(active.href)}
        className={cn(
          "glass mt-2 hidden overflow-hidden rounded-3xl border shadow-[var(--shadow-elevated)] transition-all duration-300 ease-out md:block",
          active?.menu
            ? "max-h-96 translate-y-0 border-border opacity-100"
            : "pointer-events-none max-h-0 -translate-y-1 border-transparent opacity-0"
        )}
      >
        {active?.menu && (
          <div
            className={cn(
              "grid gap-2 p-5",
              active.menu.length >= 5 ? "grid-cols-5" : active.menu.length === 4 ? "grid-cols-4" : "grid-cols-3"
            )}
          >
            {active.menu.map((item, i) => (
              <a
                key={item.label}
                href={active.href}
                onClick={() => item.tabId && setActiveTab(item.tabId)}
                className="hover-lift animate-fade-up flex items-start gap-3 rounded-2xl p-3 hover:bg-accent"
                style={{ animationDelay: `${i * 0.05}s` }}
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
                  <item.icon className="h-4 w-4" />
                </span>
                <span>
                  <span className="block text-sm font-semibold">{item.label}</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">{item.description}</span>
                </span>
              </a>
            ))}
          </div>
        )}
      </div>

      <div
        className={cn(
          "glass mt-2 overflow-hidden rounded-2xl border border-border shadow-[var(--shadow-elevated)] transition-all duration-300 ease-out md:hidden",
          open ? "max-h-80 opacity-100" : "max-h-0 border-transparent opacity-0"
        )}
      >
        <div className="flex flex-col gap-1 px-4 py-3">
          {links.map((l) => (
            <a key={l.href} href={l.href} className="rounded-md px-2 py-2 text-sm text-muted-foreground hover:bg-accent">
              {l.label}
            </a>
          ))}
          <div className="mt-2 flex items-center justify-between gap-2 px-2">
            <span className="text-sm text-muted-foreground">Theme</span>
            <ThemeToggle />
          </div>
          <div className="mt-2 flex gap-2">
            <Button variant="outline" className="flex-1 rounded-full" asChild>
              <a href={LOGIN_URL}>Log in</a>
            </Button>
            <Button variant="gradient" className="flex-1 rounded-full" asChild>
              <a href={SIGNUP_URL}>Get started</a>
            </Button>
          </div>
        </div>
      </div>
    </header>
  );
}
