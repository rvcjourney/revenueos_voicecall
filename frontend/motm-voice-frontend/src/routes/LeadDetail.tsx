import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft, Bot, CalendarCheck, FileUp, Loader2, Mail, MessageSquare, Paperclip, Pencil, Phone, Play, Plus, Reply,
  Trash2, User, X,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { CallOutcomeBadge, LeadStatusBadge } from "@/components/shared/StatusBadge";
import { useLead, useLeadsMeta, useUpdateLead } from "@/lib/hooks";
import { api, leadsApi, apiErrorMessage } from "@/lib/api";
import {
  LEAD_STATUSES, type Lead, type LeadActivity, type LeadCall, type LeadDetail as LeadDetailT,
  type LeadEmailStatus, type LeadMeetingStatus, type LeadStatus,
} from "@/lib/types";
import { formatDateTime, formatDuration, titleCase } from "@/lib/utils";

type LeadUpdate = Partial<Omit<Lead, "id" | "phone" | "owner_name">>;

export default function LeadDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const lead = useLead(id);
  const meta = useLeadsMeta();
  const updateLead = useUpdateLead();
  const qc = useQueryClient();

  async function save(data: LeadUpdate, okMessage?: string) {
    if (!id) return false;
    try {
      await updateLead.mutateAsync({ id, data });
      if (okMessage) toast.success(okMessage);
      return true;
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't save"));
      return false;
    }
  }

  async function handleDelete() {
    if (!id || !window.confirm("Delete this lead? Its calls stay in Call History.")) return;
    try {
      await leadsApi.remove(id);
      qc.invalidateQueries({ queryKey: ["leads"] });
      toast.success("Lead deleted");
      navigate("/leads");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't delete lead"));
    }
  }

  if (lead.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }
  if (lead.isError || !lead.data) {
    return <ErrorBanner error={lead.error} onRetry={() => lead.refetch()} />;
  }
  const l = lead.data;

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" onClick={() => navigate("/leads")} className="-ml-2">
        <ArrowLeft className="h-4 w-4" /> Leads
      </Button>

      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-heading text-2xl font-semibold sm:text-3xl">{l.name || l.phone}</h1>
            <LeadStatusBadge status={l.status} />
          </div>
          <p className="font-mono text-sm text-muted-foreground">
            {l.phone}{l.company ? ` · ${l.company}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={l.status} onValueChange={(v) => save({ status: v as LeadStatus })}>
            <SelectTrigger className="w-44" aria-label="Status"><SelectValue /></SelectTrigger>
            <SelectContent>
              {LEAD_STATUSES.map((s) => <SelectItem key={s} value={s}>{titleCase(s)}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={l.owner_id ?? "none"} onValueChange={(v) => save({ owner_id: v === "none" ? null : v })}>
            <SelectTrigger className="w-44" aria-label="Owner"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Unassigned</SelectItem>
              {meta.data?.members.map((m) => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button variant="outline" size="icon" onClick={handleDelete} aria-label="Delete lead">
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <CallsCard calls={l.calls} />
          <TimelineCard lead={l} />
        </div>
        <div className="space-y-6">
          <ContactCard lead={l} save={save} />
          <EmailCard lead={l} emailEnabled={!!meta.data?.email_enabled} save={save} />
          <MeetingCard lead={l} save={save} />
          <CustomFieldsCard lead={l} save={save} />
        </div>
      </div>
    </div>
  );
}

type SaveFn = (data: LeadUpdate, okMessage?: string) => Promise<boolean>;

function ContactCard({ lead, save }: { lead: LeadDetailT; save: SaveFn }) {
  const [form, setForm] = useState({ name: "", email: "", company: "" });
  useEffect(() => {
    setForm({ name: lead.name ?? "", email: lead.email ?? "", company: lead.company ?? "" });
  }, [lead.name, lead.email, lead.company]);
  const dirty = form.name !== (lead.name ?? "") || form.email !== (lead.email ?? "") || form.company !== (lead.company ?? "");

  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2 text-base"><User className="h-4 w-4" /> Contact</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {(["name", "email", "company"] as const).map((k) => (
          <div key={k} className="space-y-1.5">
            <Label htmlFor={`contact-${k}`}>{titleCase(k)}</Label>
            <Input id={`contact-${k}`} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
          </div>
        ))}
        <Button size="sm" variant="gradient" disabled={!dirty} onClick={() => save(form, "Contact saved")}>Save</Button>
      </CardContent>
    </Card>
  );
}

function EmailCard({ lead, emailEnabled, save }: { lead: LeadDetailT; emailEnabled: boolean; save: SaveFn }) {
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Mail className="h-4 w-4" /> Email</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <Select value={lead.email_status} onValueChange={(v) => save({ email_status: v as LeadEmailStatus })}>
          <SelectTrigger aria-label="Email status"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="none">Not sent</SelectItem>
            <SelectItem value="captured">Email captured</SelectItem>
            <SelectItem value="sent">Sent</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
            <SelectItem value="replied">Replied</SelectItem>
          </SelectContent>
        </Select>
        {lead.email_sent_at && <p className="text-xs text-muted-foreground">Last sent {formatDateTime(lead.email_sent_at)}</p>}
        {emailEnabled ? (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => setOpen(true)} disabled={!lead.email}>
              <Mail className="h-4 w-4" /> Send email
            </Button>
            <SendBrochureButton lead={lead} />
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            To send from here, an admin connects your company mailbox in{" "}
            <Link to="/settings" className="text-primary hover:underline">Settings → Integrations</Link>. You can still track the status.
          </p>
        )}
        {emailEnabled && !lead.email && <p className="text-xs text-muted-foreground">Add an email address above to send.</p>}
      </CardContent>
      <SendEmailDialog lead={lead} open={open} onOpenChange={setOpen} />
    </Card>
  );
}

function SendBrochureButton({ lead }: { lead: LeadDetailT }) {
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();

  async function send() {
    setBusy(true);
    try {
      const { data } = await leadsApi.sendBrochure(lead.id);
      (data.ok ? toast.success : toast.error)(data.detail);
      qc.invalidateQueries({ queryKey: ["lead", lead.id] });
      qc.invalidateQueries({ queryKey: ["leads"] });
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't send the brochure"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button size="sm" variant="outline" onClick={send} disabled={busy || !lead.email} title={lead.email ? undefined : "Add an email address first"}>
      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />} Send brochure
    </Button>
  );
}

function SendEmailDialog({ lead, open, onOpenChange }: { lead: LeadDetailT; open: boolean; onOpenChange: (v: boolean) => void }) {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("Hi {name},\n\n");
  const [sending, setSending] = useState(false);
  const qc = useQueryClient();

  async function send() {
    setSending(true);
    try {
      const { data } = await leadsApi.sendEmail(lead.id, { subject, body });
      if (data.ok) {
        toast.success("Email sent");
        onOpenChange(false);
        setSubject("");
        setBody("Hi {name},\n\n");
      } else {
        toast.error(data.detail);
      }
      qc.invalidateQueries({ queryKey: ["lead", lead.id] });
      qc.invalidateQueries({ queryKey: ["leads"] });
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't send email"));
    } finally {
      setSending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Email {lead.email}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="email-subject">Subject</Label>
            <Input id="email-subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="email-body">Message</Label>
            <Textarea id="email-body" rows={8} value={body} onChange={(e) => setBody(e.target.value)} />
            <p className="text-xs text-muted-foreground">{"{name}"} and {"{company}"} are filled in for you. Replies go to your own email.</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="gradient" onClick={send} disabled={sending || !subject.trim() || !body.trim()}>
            {sending && <Loader2 className="h-4 w-4 animate-spin" />} Send
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MeetingCard({ lead, save }: { lead: LeadDetailT; save: SaveFn }) {
  const [when, setWhen] = useState("");
  useEffect(() => setWhen(lead.meeting_at_text ?? ""), [lead.meeting_at_text]);

  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2 text-base"><CalendarCheck className="h-4 w-4" /> Meeting</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <Select value={lead.meeting_status} onValueChange={(v) => save({ meeting_status: v as LeadMeetingStatus })}>
          <SelectTrigger aria-label="Meeting status"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="none">No meeting</SelectItem>
            <SelectItem value="scheduled">Scheduled</SelectItem>
            <SelectItem value="done">Done</SelectItem>
            <SelectItem value="cancelled">Cancelled</SelectItem>
          </SelectContent>
        </Select>
        <div className="space-y-1.5">
          <Label htmlFor="meeting-when">When</Label>
          <div className="flex gap-2">
            <Input id="meeting-when" placeholder="e.g. Tuesday 4pm" value={when} onChange={(e) => setWhen(e.target.value)} />
            <Button size="sm" variant="outline" disabled={when === (lead.meeting_at_text ?? "")} onClick={() => save({ meeting_at_text: when }, "Saved")}>
              Save
            </Button>
          </div>
        </div>
        {lead.meeting_ref && <p className="text-xs text-muted-foreground">Booked by the AI agent · ref {lead.meeting_ref}</p>}
      </CardContent>
    </Card>
  );
}

function CustomFieldsCard({ lead, save }: { lead: LeadDetailT; save: SaveFn }) {
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const fields = Object.entries(lead.custom_fields);

  async function add() {
    const k = key.trim();
    if (!k) return;
    if (await save({ custom_fields: { ...lead.custom_fields, [k]: value } }, "Field added")) {
      setKey("");
      setValue("");
    }
  }

  function remove(k: string) {
    const next = { ...lead.custom_fields };
    delete next[k];
    save({ custom_fields: next });
  }

  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Pencil className="h-4 w-4" /> More details</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {fields.length === 0 && <p className="text-xs text-muted-foreground">No extra details yet. CSV columns and anything you add appear here.</p>}
        {fields.map(([k, v]) => (
          <div key={k} className="flex items-start justify-between gap-2 text-sm">
            <div className="min-w-0">
              <p className="text-xs text-muted-foreground">{titleCase(k)}</p>
              <p className="break-words">{v || "—"}</p>
            </div>
            <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={() => remove(k)} aria-label={`Remove ${k}`}>
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}
        <div className="space-y-2 border-t border-border pt-3">
          <Input placeholder="Field name, e.g. budget" value={key} onChange={(e) => setKey(e.target.value)} aria-label="New field name" />
          <Input placeholder="Value" value={value} onChange={(e) => setValue(e.target.value)} aria-label="New field value" />
          <Button size="sm" variant="outline" onClick={add} disabled={!key.trim()}><Plus className="h-4 w-4" /> Add field</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CallsCard({ calls }: { calls: LeadCall[] }) {
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Phone className="h-4 w-4" /> Calls ({calls.length})</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        {calls.length === 0 && <p className="text-sm text-muted-foreground">No calls to this number yet.</p>}
        {calls.map((c) => (
          <div key={c.id} className="space-y-2 rounded-lg border border-border p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <CallOutcomeBadge outcome={c.outcome} status={c.status} />
                <span className="text-xs text-muted-foreground">
                  {formatDateTime(c.started_at)}{c.duration_seconds ? ` · ${formatDuration(c.duration_seconds)}` : ""}
                </span>
              </div>
              <Button variant="ghost" size="sm" asChild><Link to={`/calls/${c.id}`}>Open call</Link></Button>
            </div>
            {c.summary && <p className="text-sm text-foreground/90">{c.summary}</p>}
            {c.has_recording && <RecordingPlayer callId={c.id} />}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

// The recording endpoint needs the Authorization header, which <audio src> can't
// send — fetch it as a blob on demand (same approach as CallDetail).
function RecordingPlayer({ callId }: { callId: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get(`/api/calls/${callId}/recording`, { responseType: "blob" });
      setUrl(URL.createObjectURL(res.data));
    } catch {
      toast.error("Couldn't load the recording");
    } finally {
      setLoading(false);
    }
  }

  if (url) return <audio controls autoPlay src={url} className="h-9 w-full" />;
  return (
    <Button variant="outline" size="sm" onClick={load} disabled={loading}>
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} Play recording
    </Button>
  );
}

function TimelineCard({ lead }: { lead: LeadDetailT }) {
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const qc = useQueryClient();

  async function addNote() {
    setSaving(true);
    try {
      await leadsApi.addNote(lead.id, note);
      setNote("");
      qc.invalidateQueries({ queryKey: ["lead", lead.id] });
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't save note"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2 text-base"><MessageSquare className="h-4 w-4" /> Notes & activity</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Textarea placeholder="Add a note for your team..." rows={3} value={note} onChange={(e) => setNote(e.target.value)} aria-label="New note" />
          <Button size="sm" variant="gradient" onClick={addNote} disabled={saving || !note.trim()}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />} Add note
          </Button>
        </div>
        <ol className="space-y-3 border-t border-border pt-4">
          {lead.activities.map((a) => <ActivityItem key={a.id} a={a} />)}
        </ol>
      </CardContent>
    </Card>
  );
}

function ActivityItem({ a }: { a: LeadActivity }) {
  const p = a.payload as Record<string, string | boolean | null | undefined>;
  const who =
    a.user_name ??
    (a.type === "email_reply" ? "Customer" : a.type === "email" ? "Sent automatically after the call" : "AI agent");
  let icon = <Pencil className="h-3.5 w-3.5" />;
  let text: React.ReactNode;

  switch (a.type) {
    case "call":
      icon = <Phone className="h-3.5 w-3.5" />;
      text = <>Call · {titleCase(String(p.outcome ?? ""))}{p.summary ? <span className="block text-muted-foreground">{String(p.summary)}</span> : null}</>;
      break;
    case "note":
      icon = <MessageSquare className="h-3.5 w-3.5" />;
      text = <span className="whitespace-pre-wrap">{String(p.text ?? "")}</span>;
      break;
    case "status_change":
      icon = p.by === "ai" ? <Bot className="h-3.5 w-3.5" /> : <Pencil className="h-3.5 w-3.5" />;
      text = <>Status {titleCase(String(p.from ?? ""))} → <strong>{titleCase(String(p.to ?? ""))}</strong></>;
      break;
    case "email": {
      const brochure = p.kind === "brochure";
      icon = brochure ? <Paperclip className="h-3.5 w-3.5" /> : <Mail className="h-3.5 w-3.5" />;
      const what = brochure ? `Brochure${p.file ? ` (${String(p.file)})` : ""}` : "Email";
      text = (
        <>
          {p.ok ? `${what} sent` : `${what} not sent`}
          {p.to ? ` to ${String(p.to)}` : ""}
          {!brochure && p.subject ? `: “${String(p.subject)}”` : ""}
          {!p.ok && p.detail ? <span className="block text-destructive">{String(p.detail)}</span> : null}
        </>
      );
      break;
    }
    case "email_reply":
      icon = <Reply className="h-3.5 w-3.5" />;
      text = <>Replied by email{p.subject ? `: “${String(p.subject)}”` : ""}<span className="block text-muted-foreground">from {String(p.from ?? "")}</span></>;
      break;
    case "meeting":
      icon = <CalendarCheck className="h-3.5 w-3.5" />;
      text = p.date_time
        ? <>
            Meeting booked on the call: {String(p.next_step_type ?? "meeting")} · {String(p.date_time)}{p.reference ? ` (ref ${String(p.reference)})` : ""}
            {p.calendar === "google" && (
              <span className="block text-muted-foreground">
                In Google Calendar{p.invite_sent_to ? `, invite sent to ${String(p.invite_sent_to)}` : ", no invite (no email)"}
                {p.calendar_link ? <> · <a href={String(p.calendar_link)} target="_blank" rel="noreferrer" className="underline">Open event</a></> : null}
                {p.meet_link ? <> · <a href={String(p.meet_link)} target="_blank" rel="noreferrer" className="underline">Meet link</a></> : null}
              </span>
            )}
          </>
        : <>Meeting updated: {Object.entries(p).map(([k, v]) => `${titleCase(k.replace("meeting_", ""))} ${v ?? "cleared"}`).join(", ")}</>;
      break;
    case "import":
      icon = <FileUp className="h-3.5 w-3.5" />;
      text = <>{p.created ? "Created" : "Updated"} from import {p.file ? `(${String(p.file)})` : ""}</>;
      break;
    default:
      text = p.created
        ? <>Lead added</>
        : <>Edited {Object.keys(p).map((k) => titleCase(k)).join(", ")}</>;
  }

  return (
    <li className="flex gap-3 text-sm">
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">{icon}</span>
      <div className="min-w-0 flex-1">
        <div>{text}</div>
        <p className="text-xs text-muted-foreground">{who} · {formatDateTime(a.created_at)}</p>
      </div>
    </li>
  );
}
