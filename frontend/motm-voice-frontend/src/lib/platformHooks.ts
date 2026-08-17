import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  platformAnalyticsApi,
  platformCostSettingsApi,
  platformHealthApi,
  platformMetricsApi,
  platformOrgsApi,
  platformPlansApi,
  platformVoiceCloneRequestsApi,
  unwrapPlatformList,
} from "./platformApi";
import type { PlatformOrgUpdate, PlatformPlanCreate } from "./platformTypes";

// ── Metrics ──────────────────────────────────────────────────────────────
export function usePlatformMetrics() {
  return useQuery({
    queryKey: ["platform-metrics"],
    queryFn: () => platformMetricsApi.get().then((r) => r.data),
    refetchInterval: 30_000,
  });
}

// ── Organizations ────────────────────────────────────────────────────────
export function usePlatformOrgs(params: { q?: string; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ["platform-orgs", params],
    queryFn: () => platformOrgsApi.list(params).then((r) => r.data),
  });
}

export function usePlatformOrg(id: string | undefined) {
  return useQuery({
    queryKey: ["platform-org", id],
    queryFn: () => platformOrgsApi.get(id!).then((r) => r.data),
    enabled: !!id,
  });
}

export function useUpdatePlatformOrg() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: PlatformOrgUpdate }) => platformOrgsApi.update(id, data),
    onSuccess: (_r, vars) => {
      qc.invalidateQueries({ queryKey: ["platform-orgs"] });
      qc.invalidateQueries({ queryKey: ["platform-org", vars.id] });
    },
  });
}

export function useAdjustPlatformOrgCredits() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { delta: number; reason: string } }) =>
      platformOrgsApi.adjustCredits(id, data),
    onSuccess: (_r, vars) => {
      qc.invalidateQueries({ queryKey: ["platform-org", vars.id] });
      qc.invalidateQueries({ queryKey: ["platform-orgs"] });
    },
  });
}

export function useResetPlatformOrgCredits() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => platformOrgsApi.resetCredits(id),
    onSuccess: (_r, id) => {
      qc.invalidateQueries({ queryKey: ["platform-org", id] });
      qc.invalidateQueries({ queryKey: ["platform-orgs"] });
    },
  });
}

export function usePlatformOrgInvoices(id: string | undefined) {
  return useQuery({
    queryKey: ["platform-org-invoices", id],
    queryFn: () => platformOrgsApi.invoices(id!).then((r) => r.data.invoices),
    enabled: !!id,
  });
}

// ── Plans ────────────────────────────────────────────────────────────────
export function usePlatformPlans() {
  return useQuery({
    queryKey: ["platform-plans"],
    queryFn: () => platformPlansApi.list().then((r) => unwrapPlatformList(r.data)),
  });
}

export function useCreatePlatformPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: PlatformPlanCreate) => platformPlansApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["platform-plans"] }),
  });
}

export function useUpdatePlatformPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<PlatformPlanCreate> }) => platformPlansApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["platform-plans"] }),
  });
}

// ── Usage analytics ──────────────────────────────────────────────────────
export function usePlatformUsageAnalytics() {
  return useQuery({
    queryKey: ["platform-usage-analytics"],
    queryFn: () => platformAnalyticsApi.usage().then((r) => r.data),
  });
}

export function usePlatformOrgUsageAnalytics(orgId: string | undefined) {
  return useQuery({
    queryKey: ["platform-org-usage-analytics", orgId],
    queryFn: () => platformAnalyticsApi.orgUsage(orgId!).then((r) => r.data),
    enabled: !!orgId,
  });
}

// ── Cost settings (for estimated gross margin) ──────────────────────────────
export function usePlatformCostSettings() {
  return useQuery({
    queryKey: ["platform-cost-settings"],
    queryFn: () => platformCostSettingsApi.get().then((r) => r.data),
  });
}

export function useUpdatePlatformCostSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { cost_per_minute_minor: number }) => platformCostSettingsApi.update(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["platform-cost-settings"] });
      qc.invalidateQueries({ queryKey: ["platform-usage-analytics"] });
    },
  });
}

// ── Infrastructure health ─────────────────────────────────────────────────
export function usePlatformHealth() {
  return useQuery({
    queryKey: ["platform-health"],
    queryFn: () => platformHealthApi.get().then((r) => r.data),
    refetchInterval: 30_000,
  });
}

// ── Voice clone requests ─────────────────────────────────────────────────
export function usePlatformVoiceCloneRequests(params: { status?: string; q?: string } = {}) {
  return useQuery({
    queryKey: ["platform-voice-clone-requests", params],
    queryFn: () => platformVoiceCloneRequestsApi.list(params).then((r) => unwrapPlatformList(r.data)),
  });
}

export function useApprovePlatformVoiceCloneRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => platformVoiceCloneRequestsApi.approve(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["platform-voice-clone-requests"] }),
  });
}

export function useRejectPlatformVoiceCloneRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => platformVoiceCloneRequestsApi.reject(id, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["platform-voice-clone-requests"] }),
  });
}
