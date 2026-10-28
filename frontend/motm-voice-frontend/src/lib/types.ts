// Domain types mirrored from the QuickHowl backend API contract (spec section 5.3).

export type UserRole = "admin" | "member" | "manager" | "agent";

export type CampaignGoal = "lead_generation" | "follow_up" | "survey" | "announcement";
export type CampaignStatus = "draft" | "scheduled" | "running" | "paused" | "completed" | "failed";

export type ContactStatus =
  | "pending"
  | "dialing"
  | "completed"
  | "no_answer"
  | "failed"
  | "do_not_call"
  | "queue_timeout";

export type CallDirection = "outbound" | "inbound";
export type CallStatus =
  | "initiated"
  | "ringing"
  | "connected"
  | "completed"
  | "no_answer"
  | "busy"
  | "failed"
  | "cancelled";

export type CallOutcome =
  | "interested"
  | "not_interested"
  | "callback_requested"
  | "wrong_number"
  | "do_not_call"
  | "voicemail"
  | "no_answer"
  | "pending"
  | "call_dropped";

export type CallSentiment = "positive" | "neutral" | "negative";

export type AgentAccessStatus = "approved" | "pending" | "locked";

export type DNCReason = "user_request" | "wrong_number" | "complaint" | "manual_block" | "spam_report";

export type SipTransport = "tcp" | "udp" | "tls";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  org_id: string;
  org_name: string;
}

export interface OrgQuotaInfo {
  id: string;
  name: string;
  plan_tier: string;
  monthly_call_quota: number;
  calls_used_this_period: number;
}

export interface OrgInfo extends OrgQuotaInfo {
  invite_code: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface EngineVoice {
  id: string;
  name: string;
  gender: "male" | "female";
}

// One entry of GET /api/languages.
export interface LanguageOption {
  value: string;
  label: string;
  native: string;
  cloned_voices: boolean;
  voices: EngineVoice[];
}

export interface LanguagesResponse {
  languages: LanguageOption[];
  cloning_allowed: boolean;
}

export interface AgentTemplate {
  id: string;
  name: string;
  description: string | null;
  language: string;
  /** The Greeting: spoken word for word when the call connects. */
  welcome_message: string;
  /** The Instructions (markdown with {placeholders}). */
  system_prompt: string;
  /** Default value per placeholder; a contact's CSV column wins. */
  variables: Record<string, string>;
  voice_id: string;
  llm_temperature: number;
  speech_pace: number;
  max_call_duration_seconds: number;
  created_at: string;
  access_status: AgentAccessStatus;
  access_request_id: string | null;
  can_edit: boolean;
  /** Brochure emailed when a customer agrees on a call; null = none uploaded. */
  brochure_filename: string | null;
  brochure_email_subject: string | null;
  brochure_email_body: string | null;
}

/** Google Calendar the agent books meetings into during calls. days: Monday=0 … Sunday=6. */
export interface CalendarSettings {
  duration_minutes: number;
  day_start: string;
  day_end: string;
  days: number[];
  timezone: string;
}

export interface AgentCalendar {
  /** Google sign-in is set up on this server. */
  available: boolean;
  connected: boolean;
  email: string | null;
  settings: CalendarSettings;
}

export interface AgentCreate {
  name: string;
  description?: string;
  language?: string;
  welcome_message?: string;
  system_prompt?: string;
  variables?: Record<string, string>;
  voice_id?: string;
  llm_temperature?: number;
  speech_pace?: number;
  max_call_duration_seconds?: number;
}

export interface CustomizeResult {
  summary: string;
  greeting: string;
  instructions: string;
}

export interface CampaignFolder {
  id: string;
  name: string;
  color: string | null;
  campaign_count: number;
  created_at: string;
}

export interface Campaign {
  id: string;
  name: string;
  description: string | null;
  notes: string | null;
  status: CampaignStatus;
  goal: CampaignGoal;
  folder_id: string | null;
  agent_template_id: string | null;
  total_contacts: number;
  completed_calls: number;
  interested_count: number;
  failed_count: number;
  calling_window_start: string;
  calling_window_end: string;
  calling_days: string[];
  timezone: string;
  calls_per_minute: number;
  max_retries: number;
  retry_after_minutes: number;
  start_time: string | null;
  end_time: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  created_by_name: string | null;
  language?: string | null;
  voice_id?: string | null;
  pause_reason?: string | null;
}

export interface CampaignCreate {
  name: string;
  description?: string;
  notes?: string;
  goal?: CampaignGoal;
  folder_id?: string;
  agent_template_id: string;
  sip_trunk_id?: string;
  calling_window_start?: string;
  calling_window_end?: string;
  calling_days?: string[];
  timezone?: string;
  calls_per_minute?: number;
  max_retries?: number;
  retry_after_minutes?: number;
  start_time?: string;
  end_time?: string;
  /** Speak this campaign in another language than the agent's own. Omit to inherit it. */
  language?: string;
  /** A voice for this campaign instead of the agent's own. Omit to inherit it. */
  voice_id?: string;
}

export interface CampaignContact {
  id: string;
  name: string;
  phone: string;
  email: string | null;
  company: string | null;
  custom_fields?: Record<string, unknown>;
  status: ContactStatus;
  attempt_count: number;
  last_attempted_at: string | null;
}

// GET /api/campaigns/{id}/preview: the agent's script filled in per contact.
export interface CampaignPreviewItem {
  contact_id: string;
  name: string;
  phone: string;
  welcome_message: string;
  system_prompt: string;
  missing: string[];
}

export interface CampaignPreview {
  total_contacts: number;
  variables: string[];
  /** Placeholders with no value for at least one contact. */
  missing: string[];
  items: CampaignPreviewItem[];
}

export interface TranscriptSegment {
  speaker: string;
  text: string;
  start_ms?: number;
  end_ms?: number;
}

export interface Call {
  id: string;
  campaign_id: string | null;
  phone_number: string;
  direction: CallDirection;
  status: CallStatus;
  outcome: CallOutcome;
  sentiment: CallSentiment | null;
  started_at: string | null;
  answered_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  cost_inr: number | null;
  summary: string | null;
  recording_url: string | null;
  created_at: string;
}

export interface CallListResponse {
  items: Call[];
  total: number;
  // Aggregates over the whole filtered result set (not just `items`, which is
  // capped at the request's `limit`) -- use these for summary stats, never
  // items.length/items.filter(...).
  interested_count: number;
  avg_duration_seconds: number;
}

export interface CallDetail extends Call {
  extracted_data: Record<string, unknown>;
  error_message: string | null;
  transcript_segments: TranscriptSegment[];
  transcript_full_text: string | null;
}

export interface SipTrunk {
  id: string;
  name: string;
  livekit_trunk_id: string;
  sip_domain: string;
  sip_username: string;
  caller_id: string;
  transport: SipTransport;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
  /** Left over from inbound calling (removed); only lets an admin switch it off. */
  inbound_enabled: boolean;
}

export interface SipTrunkAssignment {
  user_id: string;
  full_name: string;
  email: string;
  assigned_at: string;
}

export interface TrunkCapacity {
  trunk_id: string;
  caller_id: string;
  active_calls: number;
  max_concurrent: number;
  available_slots: number;
}

export interface DncEntry {
  id: string;
  phone_number: string;
  reason: DNCReason | string;
  notes: string | null;
  created_at: string;
}

export interface DashboardStats {
  kpis: {
    calls_today: number;
    interested_today: number;
    avg_duration_seconds: number;
    pickup_rate: number;
  };
  total_calls: number;
  total_interested: number;
  calls_last_7_days: { day: string; calls: number; interested: number }[];
  outcome_breakdown: { name: string; value: number; color: string }[];
  active_campaigns: {
    id: string;
    name: string;
    status: CampaignStatus;
    total_contacts: number;
    completed_calls: number;
    interested_count: number;
  }[];
}

export interface ConcurrencyUsage {
  in_use: number;
  max: number;
  queued: number;
  my_queued: number;
}

export interface ClonedVoice {
  id: string;
  name: string;
  voice_id: string | null;
  status: "ready" | "failed" | "pending" | "rejected";
  rejection_reason?: string | null;
  language?: string | null;
  created_at: string;
}

export interface CreditUsage {
  used: number;
  allotted: number;
  overage_minutes: number;
}

export interface PublicPlan {
  id: string;
  name: string;
  price_minor: number;
  discount_price_minor: number | null;
  currency: string;
  credits_per_month: number;
  is_custom_pricing: boolean;
  is_highlighted: boolean;
  marketing_bullets: string[];
}

export interface BillingCurrent {
  plan: PublicPlan;
  subscription_status: string | null;
  current_period_end: string | null;
  org_active: boolean;
}

export interface CheckoutResponse {
  action: "new" | "change";
  subscription_id: string | null;
  razorpay_key_id: string | null;
  plan_name: string;
  amount_minor: number;
  currency: string;
}

export interface Invoice {
  id: string;
  amount_minor: number;
  currency: string;
  status: string;
  issued_at: string | null;
  hosted_url: string | null;
}

export interface InvoiceList {
  invoices: Invoice[];
}

export interface VerifyPaymentRequest {
  razorpay_payment_id: string;
  razorpay_subscription_id: string;
  razorpay_signature: string;
}

export interface BillingAddress {
  address_line: string | null;
  city: string | null;
  state: string | null;
  pincode: string | null;
  gstin: string | null;
}

export interface TaxInvoice {
  id: string;
  invoice_number: string;
  plan_name: string;
  total_minor: number;
  currency: string;
  issued_at: string;
}

export interface TaxInvoiceList {
  invoices: TaxInvoice[];
}

export interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface UserStat {
  user_id: string;
  full_name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  total_campaigns: number;
  active_campaigns: number;
  total_calls: number;
  total_interested: number;
  last_login_at: string | null;
}

export interface OrgStats {
  totals: {
    total_members: number;
    total_campaigns: number;
    total_calls: number;
    total_interested: number;
    active_campaigns: number;
  };
  users: UserStat[];
}

export interface AgentAccessRequest {
  id: string;
  agent_id: string;
  agent_name: string;
  user_id: string;
  user_name: string;
  user_email: string;
  status: string;
  created_at: string;
}

export interface ApprovedAccess {
  request_id: string;
  user_id: string;
  user_name: string;
  user_email: string;
  agent_id: string;
  agent_name: string;
  granted_at: string;
  last_campaign_name: string | null;
  last_used_at: string | null;
  can_edit: boolean;
}

export interface AgentCreationRequest {
  id: string;
  agent_name: string;
  company_name: string;
  status: string;
  admin_notes: string | null;
  has_file: boolean;
  file_name: string | null;
  created_at: string;
}

export interface AgentCreationRequestAdmin extends AgentCreationRequest {
  user_id: string;
  user_name: string;
  user_email: string;
  product_service: string;
  target_customers: string;
  key_points: string;
  file_url: string | null;
}

export interface ActivityEvent {
  type: string;
  user_name: string;
  user_email: string;
  detail: string;
  agent_name: string;
  campaign_status: string | null;
  timestamp: string;
}

export interface ListResponse<T> {
  items: T[];
  total: number;
}

// ── Leads (internal CRM) ─────────────────────────────────────────────────
export type LeadStatus =
  | "new" | "contacted" | "interested" | "meeting_scheduled" | "qualified" | "won" | "lost" | "do_not_call";
// Pipeline order, used for the status chips and dropdowns.
export const LEAD_STATUSES: LeadStatus[] = [
  "new", "contacted", "interested", "meeting_scheduled", "qualified", "won", "lost", "do_not_call",
];
export type LeadEmailStatus = "none" | "captured" | "sent" | "failed" | "replied";
export type LeadMeetingStatus = "none" | "scheduled" | "done" | "cancelled";

export interface Lead {
  id: string;
  phone: string;
  name: string | null;
  email: string | null;
  company: string | null;
  status: LeadStatus;
  owner_id: string | null;
  owner_name: string | null;
  tags: string[];
  custom_fields: Record<string, string>;
  last_call_id: string | null;
  last_outcome: string | null;
  last_summary: string | null;
  last_called_at: string | null;
  email_status: LeadEmailStatus;
  email_sent_at: string | null;
  meeting_status: LeadMeetingStatus;
  meeting_at_text: string | null;
  meeting_ref: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeadListResponse {
  items: Lead[];
  total: number;
  status_counts: Partial<Record<LeadStatus, number>>;
}

export interface LeadActivity {
  id: string;
  type: "call" | "note" | "status_change" | "email" | "email_reply" | "meeting" | "edit" | "import";
  payload: Record<string, unknown>;
  created_at: string;
  user_name: string | null;
}

export interface LeadCall {
  id: string;
  campaign_id: string | null;
  started_at: string | null;
  status: string;
  outcome: string;
  summary: string | null;
  duration_seconds: number | null;
  has_recording: boolean;
}

export interface LeadDetail extends Lead {
  activities: LeadActivity[];
  calls: LeadCall[];
}

export interface LeadsMeta {
  members: { id: string; name: string }[];
  email_enabled: boolean;
}

export interface LeadFilters {
  status?: LeadStatus;
  owner?: string;
  q?: string;
  email_status?: LeadEmailStatus;
  meeting_status?: LeadMeetingStatus;
  limit?: number;
  offset?: number;
}

// ── Org email (SMTP) settings ────────────────────────────────────────────
export type SmtpSecurity = "ssl" | "starttls";

export interface SmtpSettings {
  /** The customer's account login (first admin), shown above the form. */
  account_email: string | null;
  sender_name: string | null;
  /** The mailbox emails go out from; also the SMTP login. */
  sender_email: string | null;
  host: string | null;
  security: SmtpSecurity | null;
  /** Optional: read replies from the same mailbox. */
  imap_host: string | null;
  has_password: boolean;
  configured: boolean;
}

export interface SmtpSettingsInput {
  sender_name: string;
  sender_email: string;
  host: string;
  security: SmtpSecurity;
  password?: string;
  imap_host: string;
}
