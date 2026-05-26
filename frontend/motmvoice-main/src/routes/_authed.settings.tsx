import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { Progress } from "@/components/ui/progress";
import { useTheme } from "@/lib/theme";
import {
  User, Users, CreditCard, Key, Phone, Bell, Palette,
  Plus, Copy, Check, Moon, Sun,
} from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_authed/settings")({
  head: () => ({ meta: [{ title: "Settings — MOTMVoice" }] }),
  component: SettingsPage,
});

// ── Tab definitions ───────────────────────────────────────────────────────────
const TABS = [
  { id: "profile",    label: "Profile",       icon: User       },
  { id: "team",       label: "Team",          icon: Users      },
  { id: "billing",    label: "Billing",       icon: CreditCard },
  { id: "api",        label: "API Keys",      icon: Key        },
  { id: "phone",      label: "Phone Numbers", icon: Phone      },
  { id: "notif",      label: "Notifications", icon: Bell       },
  { id: "appearance", label: "Appearance",    icon: Palette    },
] as const;

type TabId = (typeof TABS)[number]["id"];

function SettingsPage() {
  const { user }          = useAuth();
  const { theme, setTheme } = useTheme();
  const [active, setActive] = useState<TabId>("profile");
  const [copied, setCopied] = useState(false);

  function copyKey() {
    navigator.clipboard.writeText("sk_live_motm_a1b2c3d4e5f6");
    setCopied(true);
    toast.success("API key copied");
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">Manage your account, team, and preferences</p>
      </div>

      <div className="flex gap-8">
        {/* ── Vertical tab list ─────────────────────────────────────────────── */}
        <aside className="w-48 shrink-0 space-y-0.5">
          {TABS.map((t) => {
            const isActive = active === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setActive(t.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all text-left ${
                  isActive
                    ? "bg-primary/10 text-foreground"
                    : "text-muted-foreground hover:bg-surface-2 hover:text-foreground"
                }`}
              >
                <t.icon className={`h-4 w-4 shrink-0 ${isActive ? "text-primary" : ""}`} />
                {t.label}
              </button>
            );
          })}
        </aside>

        {/* ── Tab panels ────────────────────────────────────────────────────── */}
        <div className="flex-1 min-w-0">

          {/* Profile ──────────────────────────────────────────────────────── */}
          {active === "profile" && (
            <Panel title="Profile" subtitle="Your personal information">
              <div className="space-y-4 max-w-md">
                <Field label="Full name">
                  <Input defaultValue={user?.full_name} />
                </Field>
                <Field label="Email address">
                  <Input defaultValue={user?.email} type="email" />
                </Field>
                <Field label="Company">
                  <Input defaultValue={user?.org_name} />
                </Field>
                <Field label="New password" description="Leave blank to keep your current password">
                  <Input type="password" placeholder="••••••••" />
                </Field>
                <div className="pt-2">
                  <Button className="bg-gradient-primary text-white shadow-glow" onClick={() => toast.success("Changes saved")}>
                    Save changes
                  </Button>
                </div>
              </div>
            </Panel>
          )}

          {/* Team ─────────────────────────────────────────────────────────── */}
          {active === "team" && (
            <Panel title="Team" subtitle="Manage members and access levels">
              <div className="space-y-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-muted-foreground">3 members</span>
                  <Button size="sm" className="bg-gradient-primary text-white">
                    <Plus className="h-3.5 w-3.5" /> Invite member
                  </Button>
                </div>
                {[
                  { name: user?.full_name ?? "You", email: user?.email ?? "", role: "Admin" },
                  { name: "Priya Iyer",  email: "priya@motmvoice.ai",  role: "Sales Rep" },
                  { name: "Amit Patel",  email: "amit@motmvoice.ai",   role: "Sales Rep" },
                ].map((m) => (
                  <div key={m.email} className="flex items-center gap-3 p-3.5 rounded-xl bg-surface-2/60 border border-border">
                    <div className="h-9 w-9 rounded-full bg-gradient-primary grid place-items-center text-white text-sm font-semibold shrink-0">
                      {m.name[0].toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{m.name}</div>
                      <div className="text-xs text-muted-foreground truncate">{m.email}</div>
                    </div>
                    <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                      m.role === "Admin"
                        ? "bg-primary/15 text-primary"
                        : "bg-surface-3 text-muted-foreground"
                    }`}>
                      {m.role}
                    </span>
                  </div>
                ))}
              </div>
            </Panel>
          )}

          {/* Billing ──────────────────────────────────────────────────────── */}
          {active === "billing" && (
            <Panel title="Billing" subtitle="Your plan and usage">
              <div className="space-y-5">
                <div className="flex items-start justify-between p-5 rounded-xl bg-gradient-primary shadow-glow">
                  <div className="text-white">
                    <div className="text-xs font-medium opacity-75 uppercase tracking-wider">Current plan</div>
                    <div className="text-2xl font-bold mt-1">Growth</div>
                    <div className="text-sm opacity-80 mt-0.5">₹29,999 / month</div>
                  </div>
                  <Button variant="secondary" size="sm">Upgrade plan</Button>
                </div>

                <div className="rounded-xl bg-card border border-border p-5 space-y-3">
                  <div className="text-sm font-medium">Monthly usage</div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Calls used</span>
                    <span className="font-mono font-semibold">42,180 <span className="text-muted-foreground font-normal">/ 75,000</span></span>
                  </div>
                  <Progress value={56} className="h-2" />
                  <div className="text-xs text-muted-foreground">56% used · resets in 12 days</div>
                </div>

                <div className="rounded-xl bg-card border border-border p-5">
                  <div className="text-sm font-medium mb-3">Next invoice</div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Jun 26, 2026</span>
                    <span className="font-mono font-bold">₹29,999</span>
                  </div>
                </div>
              </div>
            </Panel>
          )}

          {/* API Keys ─────────────────────────────────────────────────────── */}
          {active === "api" && (
            <Panel title="API Keys" subtitle="Use these to connect MOTMVoice to external apps">
              <div className="space-y-4 max-w-xl">
                <div className="rounded-xl border border-border bg-surface-2/60 p-4">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-muted-foreground">Live key</span>
                    <span className="text-xs text-success">● Active</span>
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <code className="font-mono text-xs flex-1 truncate text-foreground/80">
                      sk_live_motm_a1b2c3d4e5f6…
                    </code>
                    <button
                      onClick={copyKey}
                      className="h-7 w-7 grid place-items-center rounded-md border border-border hover:bg-surface-3 text-muted-foreground hover:text-foreground transition-colors shrink-0"
                    >
                      {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                </div>
                <Button size="sm" className="bg-gradient-primary text-white">
                  <Plus className="h-3.5 w-3.5" /> Generate new key
                </Button>
                <p className="text-xs text-muted-foreground">
                  Never share your API key publicly. Regenerating will invalidate the existing key.
                </p>
              </div>
            </Panel>
          )}

          {/* Phone Numbers ────────────────────────────────────────────────── */}
          {active === "phone" && (
            <Panel title="Phone Numbers" subtitle="SIP trunk numbers assigned to your account">
              <div className="space-y-3 max-w-md">
                {[
                  { number: "+91 80691 12345", label: "Primary" },
                  { number: "+91 80691 67890", label: "Secondary" },
                ].map((p) => (
                  <div key={p.number} className="flex items-center justify-between p-4 rounded-xl bg-surface-2/60 border border-border">
                    <div>
                      <div className="font-mono text-sm font-semibold">{p.number}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">{p.label}</div>
                    </div>
                    <span className="flex items-center gap-1.5 text-xs text-success font-medium">
                      <span className="h-1.5 w-1.5 rounded-full bg-success" />
                      Active
                    </span>
                  </div>
                ))}
                <Button variant="outline" size="sm">
                  <Plus className="h-3.5 w-3.5" /> Request number
                </Button>
              </div>
            </Panel>
          )}

          {/* Notifications ────────────────────────────────────────────────── */}
          {active === "notif" && (
            <Panel title="Notifications" subtitle="Choose what you want to be notified about">
              <div className="space-y-3 max-w-md">
                {[
                  { label: "Interested lead detected",     desc: "When a call is classified as interested",     on: true  },
                  { label: "Campaign completed",           desc: "When all contacts in a campaign are called",  on: true  },
                  { label: "Call quota at 80%",            desc: "Before your monthly limit is reached",        on: true  },
                  { label: "Agent error",                  desc: "When a call fails due to a system error",     on: false },
                ].map((n) => (
                  <div key={n.label} className="flex items-center justify-between p-4 rounded-xl bg-surface-2/60 border border-border">
                    <div className="flex-1 mr-4">
                      <div className="text-sm font-medium">{n.label}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">{n.desc}</div>
                    </div>
                    <button
                      className={`relative h-5 w-9 rounded-full transition-colors ${n.on ? "bg-primary" : "bg-border"}`}
                      onClick={() => toast.info("Saved")}
                    >
                      <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${n.on ? "translate-x-4" : "translate-x-0.5"}`} />
                    </button>
                  </div>
                ))}
              </div>
            </Panel>
          )}

          {/* Appearance ───────────────────────────────────────────────────── */}
          {active === "appearance" && (
            <Panel title="Appearance" subtitle="Personalise how MOTMVoice looks for you">
              <div className="space-y-6 max-w-md">
                <div>
                  <Label className="text-sm font-medium mb-3 block">Theme</Label>
                  <div className="grid grid-cols-2 gap-4">

                    {/* Dark mode card */}
                    <button
                      type="button"
                      onClick={() => { setTheme("dark"); toast.success("Dark mode enabled"); }}
                      className={`relative rounded-xl border-2 p-3 text-left transition-all ${
                        theme === "dark"
                          ? "border-primary shadow-glow bg-primary/5"
                          : "border-border hover:border-primary/40 bg-card"
                      }`}
                    >
                      {/* Mini dark UI preview */}
                      <div className="h-24 rounded-lg overflow-hidden mb-3 bg-[oklch(0.16_0.03_265)]">
                        <div className="flex h-full">
                          <div className="w-10 bg-[oklch(0.18_0.03_265)] h-full flex flex-col gap-1.5 px-1.5 pt-2">
                            {[60, 80, 60, 70].map((w, i) => (
                              <div key={i} className="h-1.5 rounded-full bg-[oklch(0.32_0.04_265)]" style={{ width: `${w}%` }} />
                            ))}
                          </div>
                          <div className="flex-1 p-2 space-y-1.5">
                            <div className="h-2 bg-[oklch(0.32_0.04_265)] rounded w-4/5" />
                            <div className="h-2 bg-[oklch(0.26_0.04_265)] rounded w-3/5" />
                            <div className="h-5 mt-1 bg-[oklch(0.62_0.21_280)/0.3] rounded-md w-full" />
                            <div className="h-2 bg-[oklch(0.26_0.04_265)] rounded w-4/5" />
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Moon className="h-3.5 w-3.5 text-muted-foreground" />
                          <span className="text-sm font-medium">Dark</span>
                        </div>
                        {theme === "dark" && (
                          <span className="h-4 w-4 rounded-full bg-primary grid place-items-center">
                            <Check className="h-2.5 w-2.5 text-white" />
                          </span>
                        )}
                      </div>
                    </button>

                    {/* Light mode card */}
                    <button
                      type="button"
                      onClick={() => { setTheme("light"); toast.success("Light mode enabled"); }}
                      className={`relative rounded-xl border-2 p-3 text-left transition-all ${
                        theme === "light"
                          ? "border-primary shadow-glow bg-primary/5"
                          : "border-border hover:border-primary/40 bg-card"
                      }`}
                    >
                      {/* Mini light UI preview */}
                      <div className="h-24 rounded-lg overflow-hidden mb-3 bg-[oklch(0.97_0.005_250)]">
                        <div className="flex h-full">
                          <div className="w-10 bg-[oklch(0.95_0.01_250)] h-full flex flex-col gap-1.5 px-1.5 pt-2 border-r border-black/5">
                            {[60, 80, 60, 70].map((w, i) => (
                              <div key={i} className="h-1.5 rounded-full bg-[oklch(0.83_0.02_265)]" style={{ width: `${w}%` }} />
                            ))}
                          </div>
                          <div className="flex-1 p-2 space-y-1.5">
                            <div className="h-2 bg-[oklch(0.83_0.02_265)] rounded w-4/5" />
                            <div className="h-2 bg-[oklch(0.90_0.01_265)] rounded w-3/5" />
                            <div className="h-5 mt-1 bg-[oklch(0.54_0.21_280)/0.15] rounded-md w-full" />
                            <div className="h-2 bg-[oklch(0.90_0.01_265)] rounded w-4/5" />
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Sun className="h-3.5 w-3.5 text-muted-foreground" />
                          <span className="text-sm font-medium">Light</span>
                        </div>
                        {theme === "light" && (
                          <span className="h-4 w-4 rounded-full bg-primary grid place-items-center">
                            <Check className="h-2.5 w-2.5 text-white" />
                          </span>
                        )}
                      </div>
                    </button>

                  </div>
                </div>

                <div className="rounded-xl bg-surface-2/60 border border-border p-4 text-sm text-muted-foreground">
                  Your theme preference is saved automatically and will persist across sessions.
                </div>
              </div>
            </Panel>
          )}

        </div>
      </div>
    </div>
  );
}

// ── Reusable section panel ────────────────────────────────────────────────────
function Panel({
  title, subtitle, children,
}: {
  title: string; subtitle: string; children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl bg-card border border-border p-6 space-y-5">
      <div className="border-b border-border pb-4">
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>
      </div>
      {children}
    </div>
  );
}

// ── Form field helper ─────────────────────────────────────────────────────────
function Field({
  label, description, children,
}: {
  label: string; description?: string; children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-sm font-medium">{label}</Label>
      {children}
      {description && <p className="text-xs text-muted-foreground">{description}</p>}
    </div>
  );
}
