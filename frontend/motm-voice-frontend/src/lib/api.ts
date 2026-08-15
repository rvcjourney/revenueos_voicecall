import axios from "axios";
import type {
  ActivityEvent,
  AdminUser,
  AgentAccessRequest,
  AgentCreate,
  AgentCreationRequest,
  AgentCreationRequestAdmin,
  AgentTemplate,
  ApprovedAccess,
  BillingCurrent,
  Call,
  CallDetail,
  Campaign,
  CampaignContact,
  CampaignCreate,
  CampaignFolder,
  CheckoutResponse,
  ClonedVoice,
  ConcurrencyUsage,
  CreditUsage,
  DashboardStats,
  DncEntry,
  InboundAgent,
  InboundAgentCreate,
  InvoiceList,
  ListResponse,
  LoginResponse,
  OrgInfo,
  OrgQuotaInfo,
  OrgStats,
  PromptLibraryCreate,
  PromptLibraryEntry,
  PromptLibraryUpdate,
  PromptLibraryVersion,
  PublicPlan,
  SipTrunk,
  VerifyPaymentRequest,
  SipTrunkAssignment,
  TrunkCapacity,
  User,
} from "./types";

export const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const TOKEN_KEY = "motm_access_token";
export const REFRESH_TOKEN_KEY = "motm_refresh_token";
export const USER_KEY = "motm_user";

export const api = axios.create({ baseURL: API_BASE_URL, timeout: 20000 });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

// Access tokens expire every 15 minutes (backend: ACCESS_TOKEN_EXPIRE_MINUTES).
// A refresh token is already issued and stored at login, but until POST
// /api/auth/refresh existed on the backend, nothing ever redeemed it — every
// user was silently kicked to the login screen on that timer. This exchanges
// it for a new access token once per 401 and transparently retries the
// original request; a plain `axios.post` (not the `api` instance) is used for
// the network call itself so a failed refresh can't recursively re-enter this
// same interceptor.
let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) throw new Error("No refresh token stored");
  const res = await axios.post<{ access_token: string }>(`${API_BASE_URL}/api/auth/refresh`, {
    refresh_token: refreshToken,
  });
  localStorage.setItem(TOKEN_KEY, res.data.access_token);
  return res.data.access_token;
}

// Endpoints that can legitimately 401 for reasons that have nothing to do
// with an expired access token (bad password, expired/invalid refresh token
// itself) — retrying these through the refresh flow would be wrong or
// recursive, so they're excluded from the auto-retry-after-refresh below.
const _NO_REFRESH_RETRY = ["/api/auth/login", "/api/auth/refresh", "/api/auth/register", "/api/auth/verify-otp"];

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config as (typeof error.config & { _retried?: boolean }) | undefined;
    const url: string = original?.url ?? "";
    const skipRetry = _NO_REFRESH_RETRY.some((p) => url.includes(p));

    if (error.response?.status === 401 && original && !original._retried && !skipRetry) {
      original._retried = true;
      try {
        refreshPromise ??= refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
        const newToken = await refreshPromise;
        original.headers = original.headers ?? {};
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      } catch {
        clearSession();
        return Promise.reject(error);
      }
    }

    if (error.response?.status === 401) {
      clearSession();
    }
    return Promise.reject(error);
  }
);

/** True when the request failed because the backend couldn't be reached at all. */
export function isNetworkError(error: unknown): boolean {
  return axios.isAxiosError(error) && !error.response;
}

export function apiErrorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) return "Can't reach the QuickHowl server. Is the backend running?";
    const detail = error.response.data?.detail;
    if (typeof detail === "string") return detail;
    if (error.response.status === 401) return "Your session has expired. Please log in again.";
    if (error.response.status === 403) return "You don't have permission to do that.";
    if (error.response.status === 404) return "Not found.";
  }
  return fallback;
}

export async function downloadBlob(path: string, filename: string) {
  const token = localStorage.getItem(TOKEN_KEY);
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) {
    // Not an axios call, so apiErrorMessage() can't parse this — read the
    // backend's real {detail} body ourselves rather than discarding it.
    let detail = "Export failed";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // response wasn't JSON (e.g. a network-level failure) — keep the generic message
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Auth ─────────────────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    api.post<LoginResponse>("/api/auth/login", { email, password }),
  // No session yet — POST /verify-otp is what actually logs the user in,
  // once they've proven they own this email address.
  register: (data: { full_name: string; company_name: string; email: string; password: string; phone: string }) =>
    api.post<{ email: string; message: string }>("/api/auth/register", data),
  verifyOtp: (email: string, code: string) =>
    api.post<LoginResponse>("/api/auth/verify-otp", { email, code }),
  resendOtp: (email: string) => api.post("/api/auth/resend-otp", { email }),
  forgotPassword: (email: string) => api.post("/api/auth/forgot-password", { email }),
  resetPassword: (email: string, code: string, new_password: string) =>
    api.post("/api/auth/reset-password", { email, code, new_password }),
  // No session yet either — same as register(), POST /verify-otp logs them in.
  registerMember: (data: { full_name: string; email: string; password: string; org_code: string }) =>
    api.post<{ email: string; message: string }>("/api/auth/register-member", data),
  logout: () => api.post("/api/auth/logout").catch(() => undefined),
  me: () => api.get<User>("/api/auth/me"),
  updateProfile: (data: { full_name?: string; password?: string }) =>
    api.patch<User>("/api/auth/profile", data),
  orgInfo: () => api.get<OrgQuotaInfo>("/api/auth/org-info"),
};

// ── AI Agents ────────────────────────────────────────────────────────────
export const agentsApi = {
  list: () => api.get<ListResponse<AgentTemplate> | AgentTemplate[]>("/api/agents"),
  get: (id: string) => api.get<AgentTemplate>(`/api/agents/${id}`),
  create: (data: AgentCreate) => api.post<AgentTemplate>("/api/agents", data),
  update: (id: string, data: Partial<AgentCreate>) => api.patch<AgentTemplate>(`/api/agents/${id}`, data),
  remove: (id: string) => api.delete(`/api/agents/${id}`),
  requestAccess: (id: string) => api.post<{ message: string }>(`/api/agents/${id}/request-access`),
  testCall: (id: string, phone_number: string, trunk_id?: string) =>
    api.post<{ call_id: string; status: string }>(`/api/agents/${id}/test-call`, { phone_number, trunk_id }),
  tryNow: (phone_number: string) =>
    api.post<{ call_id: string; status: string }>("/api/agents/try-now", { phone_number }),
  optimizePrompt: (raw_input: string) =>
    api.post<{ optimized_prompt: string }>("/api/agents/optimize-prompt", { raw_input }),
  requestCreation: (form: FormData) =>
    api.post<{ id: string; message: string }>("/api/agents/creation-request", form, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  myCreationRequests: () => api.get<AgentCreationRequest[]>("/api/agents/my-creation-requests"),
};

// ── Prompt library ───────────────────────────────────────────────────────
export const promptLibraryApi = {
  list: (params?: { q?: string; tag?: string }) =>
    api.get<ListResponse<PromptLibraryEntry>>("/api/prompt-library", { params }),
  create: (data: PromptLibraryCreate) => api.post<PromptLibraryEntry>("/api/prompt-library", data),
  update: (id: string, data: PromptLibraryUpdate) =>
    api.patch<PromptLibraryEntry>(`/api/prompt-library/${id}`, data),
  remove: (id: string) => api.delete(`/api/prompt-library/${id}`),
  history: (id: string) => api.get<PromptLibraryVersion[]>(`/api/prompt-library/${id}/history`),
  restore: (id: string, version: number) =>
    api.post<PromptLibraryEntry>(`/api/prompt-library/${id}/restore/${version}`),
  markPerformance: (id: string, is_high_performing: boolean) =>
    api.patch<PromptLibraryEntry>(`/api/prompt-library/${id}/performance`, { is_high_performing }),
  syncFromAgents: () =>
    api.post<{ created: number; message: string }>("/api/prompt-library/sync-from-agents"),
};

// ── Inbound Agents (answer calls arriving on a number) ────────────────────
export const inboundAgentsApi = {
  list: () => api.get<ListResponse<InboundAgent> | InboundAgent[]>("/api/inbound-agents"),
  get: (id: string) => api.get<InboundAgent>(`/api/inbound-agents/${id}`),
  create: (data: InboundAgentCreate) => api.post<InboundAgent>("/api/inbound-agents", data),
  update: (id: string, data: Partial<InboundAgentCreate>) =>
    api.patch<InboundAgent>(`/api/inbound-agents/${id}`, data),
  remove: (id: string) => api.delete(`/api/inbound-agents/${id}`),
};

// ── Campaigns ────────────────────────────────────────────────────────────
export const campaignsApi = {
  list: (params?: { status?: string; folder_id?: string }) =>
    api.get<ListResponse<Campaign> | Campaign[]>("/api/campaigns", { params }),
  get: (id: string) => api.get<Campaign>(`/api/campaigns/${id}`),
  create: (data: CampaignCreate) => api.post<Campaign>("/api/campaigns", data),
  update: (id: string, data: Partial<Campaign>) => api.patch<Campaign>(`/api/campaigns/${id}`, data),
  remove: (id: string) => api.delete(`/api/campaigns/${id}`),
  contacts: (id: string, params?: { status?: string; limit?: number; offset?: number }) =>
    api.get<ListResponse<CampaignContact>>(`/api/campaigns/${id}/contacts`, { params }),
  uploadContacts: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<{ count: number; message: string }>(`/api/campaigns/${id}/contacts`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  launch: (id: string) => api.post<Campaign>(`/api/campaigns/${id}/launch`),
  pause: (id: string) => api.post<Campaign>(`/api/campaigns/${id}/pause`),
  duplicate: (id: string) => api.post<Campaign>(`/api/campaigns/${id}/duplicate`),
  exportInterested: (id: string, filename = "interested-leads.csv") =>
    downloadBlob(`/api/campaigns/${id}/export/interested`, filename),
  exportNoAnswer: (id: string, filename = "no-answer.csv") =>
    downloadBlob(`/api/campaigns/${id}/export/no_answer`, filename),
  exportCallbacks: (id: string, filename = "callback-requests.csv") =>
    downloadBlob(`/api/campaigns/${id}/export/callback_requested`, filename),
  exportAll: (id: string, filename = "all-results.csv") =>
    downloadBlob(`/api/campaigns/${id}/export/all`, filename),
};

// ── Folders ──────────────────────────────────────────────────────────────
export const foldersApi = {
  list: () => api.get<ListResponse<CampaignFolder> | CampaignFolder[]>("/api/folders"),
  create: (data: { name: string; color?: string }) => api.post<CampaignFolder>("/api/folders", data),
  update: (id: string, data: { name?: string; color?: string }) =>
    api.patch<CampaignFolder>(`/api/folders/${id}`, data),
  remove: (id: string) => api.delete(`/api/folders/${id}`),
};

// ── Calls ────────────────────────────────────────────────────────────────
export const callsApi = {
  list: (params?: { campaign_id?: string; outcome?: string; limit?: number; offset?: number }) =>
    api.get<ListResponse<Call> | Call[]>("/api/calls", { params }),
  get: (id: string) => api.get<CallDetail>(`/api/calls/${id}`),
  fetchRecording: (id: string) =>
    api.post<{ found: boolean; recording_url?: string }>(`/api/calls/${id}/fetch-recording`),
  recordingUrl: (id: string, download = false) =>
    `${API_BASE_URL}/api/calls/${id}/recording${download ? "?download=true" : ""}`,
};

// ── Analytics & usage ────────────────────────────────────────────────────
export const analyticsApi = {
  dashboard: () => api.get<DashboardStats>("/api/analytics/dashboard"),
};

export const usageApi = {
  concurrency: () => api.get<ConcurrencyUsage>("/api/usage/concurrency"),
  credits: () => api.get<CreditUsage>("/api/usage/credits"),
};

// ── Public pricing & billing ─────────────────────────────────────────────
export const plansApi = {
  list: () => api.get<PublicPlan[]>("/api/plans"),
};

export const billingApi = {
  current: () => api.get<BillingCurrent>("/api/billing/current"),
  checkout: (planId: string) => api.post<CheckoutResponse>("/api/billing/checkout", { plan_id: planId }),
  verifyPayment: (data: VerifyPaymentRequest) =>
    api.post<{ verified: boolean }>("/api/billing/verify-payment", data),
  cancel: () => api.post<{ status: string }>("/api/billing/cancel"),
  invoices: () => api.get<InvoiceList>("/api/billing/invoices"),
};

// ── Voice cloning ────────────────────────────────────────────────────────
export const voiceCloningApi = {
  list: () => api.get<ListResponse<ClonedVoice> | ClonedVoice[]>("/api/voice-cloning"),
  create: (data: { name: string; file: File; consentVideo: File }) => {
    const form = new FormData();
    form.append("name", data.name);
    form.append("file", data.file);
    form.append("consent_video", data.consentVideo);
    return api.post<ClonedVoice>("/api/voice-cloning", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  remove: (id: string) => api.delete(`/api/voice-cloning/${id}`),
};

// ── SIP trunks / phone numbers ───────────────────────────────────────────
export const sipTrunksApi = {
  list: () => api.get<ListResponse<SipTrunk> | SipTrunk[]>("/api/sip-trunks"),
  create: (data: Partial<SipTrunk>) => api.post<SipTrunk>("/api/sip-trunks", data),
  update: (id: string, data: Partial<SipTrunk>) => api.put<SipTrunk>(`/api/sip-trunks/${id}`, data),
  remove: (id: string) => api.delete(`/api/sip-trunks/${id}`),
  assign: (id: string, user_id: string) => api.post(`/api/sip-trunks/${id}/assign`, { user_id }),
  unassign: (id: string, userId: string) => api.delete(`/api/sip-trunks/${id}/assign/${userId}`),
  assignments: (id: string) => api.get<SipTrunkAssignment[]>(`/api/sip-trunks/${id}/assignments`),
  connectVobiz: (data: { auth_id: string; auth_token: string; did: string }) =>
    api.post<{ trunk_id: string; status: string; did: string }>("/api/sip-trunks/connect-vobiz", data),
  test: (id: string) => api.post<{ is_active: boolean }>(`/api/sip-trunks/${id}/test`),
  capacity: () => api.get<TrunkCapacity[]>("/api/sip-trunks/capacity"),
  my: () => api.get<ListResponse<SipTrunk> | SipTrunk[]>("/api/sip-trunks/my"),
  setupInbound: (trunkId: string, inbound_agent_template_id: string) =>
    api.post<{ trunk_id: string; inbound_enabled: boolean; inbound_agent_template_id: string | null }>(
      `/api/sip-trunks/${trunkId}/inbound`,
      { inbound_agent_template_id }
    ),
  updateInboundAgent: (trunkId: string, inbound_agent_template_id: string) =>
    api.patch<{ trunk_id: string; inbound_enabled: boolean; inbound_agent_template_id: string | null }>(
      `/api/sip-trunks/${trunkId}/inbound`,
      { inbound_agent_template_id }
    ),
  disableInbound: (trunkId: string) =>
    api.delete<{ trunk_id: string; inbound_enabled: boolean; inbound_agent_template_id: string | null }>(
      `/api/sip-trunks/${trunkId}/inbound`
    ),
};

// ── Admin ────────────────────────────────────────────────────────────────
export const adminApi = {
  org: () => api.get<OrgInfo>("/api/admin/org"),
  stats: () => api.get<OrgStats>("/api/admin/stats"),
  users: () => api.get<AdminUser[]>("/api/admin/users"),
  createUser: (data: { full_name: string; email: string; password: string; role: string }) =>
    api.post<AdminUser>("/api/admin/users", data),
  updateUser: (id: string, data: { full_name?: string; role?: string; is_active?: boolean }) =>
    api.patch<AdminUser>(`/api/admin/users/${id}`, data),
  removeUser: (id: string) => api.delete(`/api/admin/users/${id}`),
  agentRequests: (status?: string) =>
    api.get<AgentAccessRequest[]>("/api/admin/agent-requests", { params: { status } }),
  approveAgentRequest: (id: string) => api.post(`/api/admin/agent-requests/${id}/approve`),
  rejectAgentRequest: (id: string) => api.post(`/api/admin/agent-requests/${id}/reject`),
  revokeAgentAccess: (id: string) => api.post(`/api/admin/agent-requests/${id}/revoke`),
  agentAccess: () => api.get<ApprovedAccess[]>("/api/admin/agent-access"),
  setEditPermission: (id: string, can_edit: boolean) =>
    api.patch(`/api/admin/agent-access/${id}/edit-permission`, { can_edit }),
  activity: () => api.get<ActivityEvent[]>("/api/admin/activity"),
  dnc: (q?: string) => api.get<DncEntry[]>("/api/admin/dnc", { params: q ? { q } : undefined }),
  addDnc: (data: { phone_number: string; notes?: string }) => api.post<DncEntry>("/api/admin/dnc", data),
  removeDnc: (id: string) => api.delete(`/api/admin/dnc/${id}`),
  agentCreationRequests: (status?: string) =>
    api.get<AgentCreationRequestAdmin[]>("/api/admin/agent-creation-requests", { params: { status } }),
  reviewAgentCreationRequest: (id: string, admin_notes?: string) =>
    api.patch(`/api/admin/agent-creation-requests/${id}/review`, { admin_notes }),
  downloadCreationRequestFile: (id: string, filename: string) =>
    downloadBlob(`/api/admin/agent-creation-requests/${id}/file`, filename),
};

/** Normalizes list endpoints that may return either a bare array or { items, total }. */
export function unwrapList<T>(data: ListResponse<T> | T[] | undefined): T[] {
  if (!data) return [];
  return Array.isArray(data) ? data : data.items;
}
