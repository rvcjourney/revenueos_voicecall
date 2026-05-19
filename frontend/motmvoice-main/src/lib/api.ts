import axios from "axios";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const api = axios.create({ baseURL: BASE });

// Attach JWT on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("motm_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// On 401, clear auth tokens — the route guard handles redirect naturally
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("motm_token");
      localStorage.removeItem("motm_user");
      // Don't hard-redirect here — the _authed route guard will redirect if needed
    }
    return Promise.reject(err);
  }
);

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    api.post<LoginResponse>("/api/auth/login", { email, password }),
  register: (data: RegisterRequest) =>
    api.post<LoginResponse>("/api/auth/register", data),
  me: () => api.get<UserOut>("/api/auth/me"),
};

// ── Campaigns ─────────────────────────────────────────────────────────────────
export const campaignsApi = {
  list: (status?: string) =>
    api.get<ListResponse<CampaignOut>>("/api/campaigns", { params: { status } }),
  get: (id: string) => api.get<CampaignOut>(`/api/campaigns/${id}`),
  create: (data: CampaignCreate) => api.post<CampaignOut>("/api/campaigns", data),
  update: (id: string, data: Partial<CampaignOut>) =>
    api.patch<CampaignOut>(`/api/campaigns/${id}`, data),
  delete: (id: string) => api.delete(`/api/campaigns/${id}`),
  uploadContacts: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<{ count: number; message: string }>(
      `/api/campaigns/${id}/contacts`,
      form
    );
  },
  getContacts: (id: string, params?: { status?: string; limit?: number; offset?: number }) =>
    api.get<{ items: ContactOut[]; total: number }>(`/api/campaigns/${id}/contacts`, { params }),
  launch: (id: string) => api.post<CampaignOut>(`/api/campaigns/${id}/launch`),
  pause: (id: string) => api.post<CampaignOut>(`/api/campaigns/${id}/pause`),
  exportNoAnswerCalls: async (id: string, filename: string) => {
    const token = localStorage.getItem("motm_token");
    const res = await fetch(`${BASE}/api/campaigns/${id}/export/no_answer`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error("Export failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
  exportInterestedLeads: async (id: string, filename: string) => {
    const token = localStorage.getItem("motm_token");
    const res = await fetch(`${BASE}/api/campaigns/${id}/export/interested`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error("Export failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
};

// ── Calls ─────────────────────────────────────────────────────────────────────
export const callsApi = {
  list: (params?: { campaign_id?: string; outcome?: string; limit?: number; offset?: number }) =>
    api.get<ListResponse<CallOut>>("/api/calls", { params }),
  get: (id: string) => api.get<CallDetail>(`/api/calls/${id}`),
};

// ── Agents ────────────────────────────────────────────────────────────────────
export const agentsApi = {
  list: () => api.get<ListResponse<AgentOut>>("/api/agents"),
  get: (id: string) => api.get<AgentOut>(`/api/agents/${id}`),
  create: (data: AgentCreate) => api.post<AgentOut>("/api/agents", data),
  update: (id: string, data: Partial<AgentOut>) =>
    api.patch<AgentOut>(`/api/agents/${id}`, data),
  delete: (id: string) => api.delete(`/api/agents/${id}`),
};

// ── Analytics ─────────────────────────────────────────────────────────────────
export const analyticsApi = {
  dashboard: () => api.get<DashboardStats>("/api/analytics/dashboard"),
};

// ── Types ─────────────────────────────────────────────────────────────────────
export interface UserOut {
  id: string;
  email: string;
  full_name: string;
  role: string;
  org_id: string;
  org_name: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: UserOut;
}

export interface RegisterRequest {
  full_name: string;
  company_name: string;
  email: string;
  password: string;
  phone?: string;
}

export interface ListResponse<T> {
  items: T[];
  total: number;
}

export interface CampaignOut {
  id: string;
  name: string;
  description: string | null;
  status: string;
  goal: string;
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
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface CampaignCreate {
  name: string;
  description?: string;
  goal?: string;
  agent_template_id: string;
  calling_window_start?: string;
  calling_window_end?: string;
  calling_days?: string[];
  timezone?: string;
  calls_per_minute?: number;
  max_retries?: number;
  retry_after_minutes?: number;
}

export interface CallOut {
  id: string;
  campaign_id: string | null;
  phone_number: string;
  direction: string;
  status: string;
  outcome: string;
  sentiment: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  cost_inr: number | null;
  summary: string | null;
  recording_url: string | null;
  created_at: string;
}

export interface CallDetail extends CallOut {
  recording_url: string | null;
  extracted_data: Record<string, unknown>;
  error_message: string | null;
  transcript_segments: { speaker: string; text: string; start_ms?: number; end_ms?: number }[];
  transcript_full_text: string | null;
}

export interface AgentOut {
  id: string;
  name: string;
  description: string | null;
  language: string;
  welcome_message: string;
  system_prompt: string;
  voice_id: string;
  voice_provider: string;
  llm_model: string;
  llm_temperature: number;
  max_call_duration_seconds: number;
  created_at: string;
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

export interface ContactOut {
  id: string;
  name: string;
  phone: string;
  email: string | null;
  company: string | null;
  status: string;
  attempt_count: number;
  last_attempted_at: string | null;
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
    status: string;
    total_contacts: number;
    completed_calls: number;
    interested_count: number;
  }[];
}
