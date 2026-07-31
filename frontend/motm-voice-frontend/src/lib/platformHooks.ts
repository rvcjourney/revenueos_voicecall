import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { platformMetricsApi, platformOrgsApi, platformPlansApi, unwrapPlatformList } from "./platformApi";
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
