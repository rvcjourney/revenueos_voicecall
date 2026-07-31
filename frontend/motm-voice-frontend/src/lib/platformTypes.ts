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
}

export interface PlatformListResponse<T> {
  items: T[];
  total: number;
}
