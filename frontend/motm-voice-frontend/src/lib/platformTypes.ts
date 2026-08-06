// Domain types for the SuperAdmin / Platform Console — talks only to /api/platform/*.
// Kept separate from ./types.ts (the tenant-facing contract) on purpose.

export interface PlatformAdmin {
  id: string;
  email: string;
  full_name: string;
}

export interface PlatformLoginResponse {
  access_token: string;
  token_type: string;
  admin: PlatformAdmin;
}

export interface PlatformMetrics {
  org_count: number;
  active_campaigns: number;
  total_calls_used: number;
}

export interface PlatformOrg {
  id: string;
  name: string;
  slug: string;
  plan_name: string;
  is_active: boolean;
  calls_used_this_period: number;
  monthly_call_quota: number;
  created_at: string;
}

export interface PlatformOrgDetail extends PlatformOrg {
  users_count: number;
  subscription_status: string;
  subscription_current_period_end: string | null;
  credits_used_this_period: number;
  credits_per_month: number;
  elevenlabs_enabled: boolean;
}

export interface PlatformOrgUpdate {
  is_active?: boolean;
  plan_id?: string;
  monthly_call_quota?: number;
  elevenlabs_enabled?: boolean;
}

export interface PlatformPlan {
  id: string;
  name: string;
  price_minor: number;
  currency: string;
  monthly_call_quota: number;
  max_concurrent_calls: number;
  credits_per_month: number;
  credit_price_cents: number;
  features: Record<string, string>;
  is_active: boolean;
  discount_price_minor: number | null;
  is_custom_pricing: boolean;
  is_highlighted: boolean;
  marketing_bullets: string[];
}

export interface PlatformPlanCreate {
  name: string;
  price_minor: number;
  currency?: string;
  monthly_call_quota: number;
  max_concurrent_calls: number;
  credits_per_month?: number;
  credit_price_cents?: number;
  features?: Record<string, string>;
  is_active?: boolean;
  discount_price_minor?: number | null;
  is_custom_pricing?: boolean;
  is_highlighted?: boolean;
  marketing_bullets?: string[];
}

export interface PlatformCostSettings {
  cost_per_minute_minor: number;
  currency: string;
}

export interface PlatformListResponse<T> {
  items: T[];
  total: number;
}

export interface PlatformUsagePoint {
  day: string;
  calls: number;
  credits: number;
}

export interface PlatformUsageAnalytics {
  series: PlatformUsagePoint[];
  mrr_minor: number;
  currency: string;
  average_plan_price_minor: number;
  cost_per_minute_minor: number;
  estimated_cogs_minor_30d: number;
  estimated_gross_margin_minor: number;
  estimated_margin_percent: number;
}

export interface PlatformHealth {
  api: boolean;
  database: boolean;
  redis: boolean;
  celery_workers_online: number;
  celery_worker_names: string[];
  elevenlabs_ok: boolean;
  elevenlabs_tier: string | null;
  elevenlabs_characters_used: number | null;
  elevenlabs_characters_limit: number | null;
  elevenlabs_next_reset_unix: number | null;
  db_size_bytes: number;
  db_size_limit_bytes: number;
  db_connections_current: number;
  db_connections_max: number;
  db_tables_missing_rls: string[];
}

export interface PlatformVoiceCloneRequest {
  id: string;
  org_id: string;
  org_name: string;
  user_name: string | null;
  user_email: string | null;
  name: string;
  audio_url: string;
  video_url: string;
  status: "pending" | "approved" | "rejected";
  rejection_reason: string | null;
  reviewed_at: string | null;
  created_at: string;
}
