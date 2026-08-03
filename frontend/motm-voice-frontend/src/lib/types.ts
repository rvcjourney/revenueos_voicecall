// Domain types mirrored from the Talkryn backend API contract (spec section 5.3).

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
  | "pending";

export type CallSentiment = "positive" | "neutral" | "negative";

export type AgentAccessStatus = "approved" | "pending" | "locked";

export type VoiceProvider = "elevenlabs" | "cartesia" | "sarvam" | "chatterbox";

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

export interface AgentTemplate {
  id: string;
  name: string;
  description: string | null;
  language: string;
  welcome_message: string;
  system_prompt: string;
  voice_id: string;
  voice_provider: VoiceProvider | string;
  llm_model: string;
  llm_temperature: number;
  max_call_duration_seconds: number;
  created_at: string;
  access_status: AgentAccessStatus;
  access_request_id: string | null;
  can_edit: boolean;
}

export interface AgentCreate {
  name: string;
  description?: string;
  language?: string;
  welcome_message?: string;
  system_prompt?: string;
  voice_id?: string;
  voice_provider?: string;
  llm_model?: string;
  llm_temperature?: number;
  max_call_duration_seconds?: number;
}

// ── Inbound agents (answer calls arriving on a number, kept separate from
// outbound campaign/test-call AgentTemplate) ────────────────────────────────
export interface InboundAgent {
  id: string;
  name: string;
  description: string | null;
  language: string;
  welcome_message: string;
  system_prompt: string;
  voice_id: string;
  voice_provider: VoiceProvider | string;
  llm_model: string;
  llm_temperature: number;
  max_call_duration_seconds: number;
  created_at: string;
}

export interface InboundAgentCreate {
  name: string;
  description?: string;
  language?: string;
  welcome_message?: string;
  system_prompt?: string;
  voice_id?: string;
  voice_provider?: string;
  llm_model?: string;
  llm_temperature?: number;
  max_call_duration_seconds?: number;
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
  agent_template_id: string;
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
  ended_at: string | null;
  duration_seconds: number | null;
  cost_inr: number | null;
  summary: string | null;
  recording_url: string | null;
  created_at: string;
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
  inbound_enabled: boolean;
  inbound_agent_template_id: string | null;
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
}

export interface ClonedVoice {
  id: string;
  name: string;
  elevenlabs_voice_id: string | null;
  status: "ready" | "failed" | "pending" | "rejected";
  rejection_reason?: string | null;
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
}

export interface CheckoutResponse {
  action: "new" | "change";
  subscription_id: string | null;
  razorpay_key_id: string | null;
  plan_name: string;
  amount_minor: number;
  currency: string;
}

export interface VerifyPaymentRequest {
  razorpay_payment_id: string;
  razorpay_subscription_id: string;
  razorpay_signature: string;
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
