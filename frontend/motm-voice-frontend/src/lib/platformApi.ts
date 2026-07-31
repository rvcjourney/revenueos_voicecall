import axios from "axios";
import type {
  PlatformListResponse,
  PlatformLoginResponse,
  PlatformMetrics,
  PlatformOrg,
  PlatformOrgDetail,
  PlatformOrgUpdate,
  PlatformPlan,
  PlatformPlanCreate,
} from "./platformTypes";

// Separate axios instance + storage keys from the tenant app's `api`/TOKEN_KEY in
// ./api.ts. Platform tokens carry `scope: "platform"` and are rejected by tenant
// auth endpoints (and vice versa), so client-side storage mirrors that split —
// a platform admin session must never share state with a tenant session.
export const PLATFORM_API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const PLATFORM_TOKEN_KEY = "platform_access_token";
export const PLATFORM_ADMIN_KEY = "platform_admin";

export const platformApi = axios.create({ baseURL: PLATFORM_API_BASE_URL, timeout: 20000 });

platformApi.interceptors.request.use((config) => {
  const token = localStorage.getItem(PLATFORM_TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler = () => {};

/** Lets PlatformAuthProvider react (clear in-memory state) when a 401 clears storage. */
export function setPlatformUnauthorizedHandler(handler: UnauthorizedHandler) {
  onUnauthorized = handler;
}

platformApi.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(PLATFORM_TOKEN_KEY);
      localStorage.removeItem(PLATFORM_ADMIN_KEY);
      onUnauthorized();
    }
    return Promise.reject(error);
  }
);

export function isPlatformNetworkError(error: unknown): boolean {
  return axios.isAxiosError(error) && !error.response;
}

export function platformApiErrorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) return "Can't reach the platform API. Is the backend running?";
    const detail = error.response.data?.detail;
    if (typeof detail === "string") return detail;
    if (error.response.status === 401) return "Your session has expired. Please log in again.";
    if (error.response.status === 403) return "You don't have permission to do that.";
    if (error.response.status === 404) return "Not found.";
  }
  return fallback;
}

// ── Auth ─────────────────────────────────────────────────────────────────
export const platformAuthApi = {
  login: (email: string, password: string) =>
    platformApi.post<PlatformLoginResponse>("/api/platform/login", { email, password }),
};

// ── Metrics ──────────────────────────────────────────────────────────────
export const platformMetricsApi = {
  get: () => platformApi.get<PlatformMetrics>("/api/platform/metrics"),
};

// ── Organizations ────────────────────────────────────────────────────────
export const platformOrgsApi = {
  list: (params?: { q?: string; limit?: number; offset?: number }) =>
    platformApi.get<PlatformListResponse<PlatformOrg>>("/api/platform/orgs", { params }),
  get: (id: string) => platformApi.get<PlatformOrgDetail>(`/api/platform/orgs/${id}`),
  update: (id: string, data: PlatformOrgUpdate) =>
    platformApi.patch<PlatformOrgDetail>(`/api/platform/orgs/${id}`, data),
  adjustCredits: (id: string, data: { delta: number; reason: string }) =>
    platformApi.post<PlatformOrgDetail>(`/api/platform/orgs/${id}/credits/adjust`, data),
  resetCredits: (id: string) => platformApi.post<PlatformOrgDetail>(`/api/platform/orgs/${id}/credits/reset`),
};

// ── Plans ────────────────────────────────────────────────────────────────
export const platformPlansApi = {
  list: () => platformApi.get<PlatformListResponse<PlatformPlan> | PlatformPlan[]>("/api/platform/plans"),
  create: (data: PlatformPlanCreate) => platformApi.post<PlatformPlan>("/api/platform/plans", data),
  update: (id: string, data: Partial<PlatformPlanCreate>) =>
    platformApi.patch<PlatformPlan>(`/api/platform/plans/${id}`, data),
};

export function unwrapPlatformList<T>(data: PlatformListResponse<T> | T[] | undefined): T[] {
  if (!data) return [];
  return Array.isArray(data) ? data : data.items;
}
