import { createFileRoute, useNavigate } from "@tanstack/react-router";
import React, { useState, useEffect } from "react";
import { adminApi, type ActivityEvent } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { ClipboardList, Search, Loader2, RefreshCw, Megaphone, Bot, CheckCircle, XCircle, Clock, Play } from "lucide-react";

export const Route = createFileRoute("/_authed/admin/audit")({
  head: () => ({ meta: [{ title: "Audit Log — MOTMVoice" }] }),
  component: AuditPage,
});

function eventMeta(type: string): { icon: React.ElementType; color: string; label: string } {
  switch (type) {
    case "campaign_created":   return { icon: Megaphone,    color: "text-primary",       label: "Campaign Created"   };
    case "campaign_launched":  return { icon: Play,         color: "text-success",       label: "Campaign Launched"  };
    case "campaign_completed": return { icon: CheckCircle,  color: "text-success",       label: "Campaign Completed" };
    case "agent_access_approved":  return { icon: Bot,      color: "text-primary",       label: "Agent Access Approved" };
    case "agent_access_rejected":  return { icon: XCircle,  color: "text-destructive",   label: "Agent Access Rejected" };
    case "agent_access_pending":   return { icon: Clock,    color: "text-amber-400",     label: "Agent Access Requested" };
    default:                   return { icon: ClipboardList,color: "text-muted-foreground", label: type.replace(/_/g, " ") };
  }
}

function formatRelative(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60)  return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60)  return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function AuditPage() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();

  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");

  useEffect(() => {
    if (!isAdmin) navigate({ to: "/dashboard" });
  }, [isAdmin, navigate]);

  async function load() {
    setLoading(true);
    try {
      const { data } = await adminApi.getActivity();
      setEvents(data);
    } catch {
      toast.error("Failed to load audit log");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const filtered = events.filter((e) => {
    const matchesQ = !q || e.user_name.toLowerCase().includes(q.toLowerCase()) ||
      e.detail.toLowerCase().includes(q.toLowerCase()) ||
      e.user_email.toLowerCase().includes(q.toLowerCase());
    const matchesType = typeFilter === "all" || e.type.startsWith(typeFilter);
    return matchesQ && matchesType;
  });

  const EVENT_TYPES = [
    { value: "all",      label: "All Events"      },
    { value: "campaign", label: "Campaigns"        },
    { value: "agent",    label: "Agent Access"     },
  ];

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ClipboardList className="h-6 w-6 text-primary" />
            Audit Log
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            All platform activity for your organisation — last 60 events.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search user, campaign…"
            className="pl-9"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <div className="flex gap-1">
          {EVENT_TYPES.map((t) => (
            <button
              key={t.value}
              onClick={() => setTypeFilter(t.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
                typeFilter === t.value
                  ? "bg-primary/20 border-primary/60 text-primary"
                  : "border-border text-muted-foreground hover:border-primary/40"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <span className="text-xs text-muted-foreground">{filtered.length} events</span>
      </div>

      {/* Table */}
      <div className="rounded-xl bg-card border border-border overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center">
            <ClipboardList className="h-10 w-10 mx-auto text-muted-foreground/30 mb-3" />
            <p className="text-muted-foreground text-sm">No events match your filter</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground bg-surface-2/40">
                  <th className="px-4 py-2.5 font-medium">Event</th>
                  <th className="px-4 py-2.5 font-medium">User</th>
                  <th className="px-4 py-2.5 font-medium">Detail</th>
                  <th className="px-4 py-2.5 font-medium">Agent</th>
                  <th className="px-4 py-2.5 font-medium text-right">When</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((e, i) => {
                  const meta = eventMeta(e.type);
                  const Icon = meta.icon;
                  return (
                    <tr key={i} className="border-t border-border/60 hover:bg-surface-2/30">
                      <td className="px-4 py-3">
                        <div className={`flex items-center gap-2 text-xs font-semibold ${meta.color}`}>
                          <Icon className="h-3.5 w-3.5 shrink-0" />
                          {meta.label}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-xs font-medium">{e.user_name}</div>
                        <div className="text-xs text-muted-foreground">{e.user_email}</div>
                      </td>
                      <td className="px-4 py-3 text-xs max-w-[200px] truncate" title={e.detail}>
                        {e.detail}
                        {e.campaign_status && (
                          <span className="ml-1.5 text-muted-foreground">({e.campaign_status})</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{e.agent_name || "—"}</td>
                      <td className="px-4 py-3 text-right">
                        <div className="text-xs text-muted-foreground" title={new Date(e.timestamp).toLocaleString()}>
                          {formatRelative(e.timestamp)}
                        </div>
                        <div className="text-[10px] text-muted-foreground/60">
                          {new Date(e.timestamp).toLocaleDateString()}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
