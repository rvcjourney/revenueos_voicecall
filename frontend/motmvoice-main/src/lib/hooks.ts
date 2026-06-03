import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { agentsApi, analyticsApi, callsApi, campaignsApi, foldersApi, type AgentCreate, type CampaignCreate } from "@/lib/api";

export function useCampaignContacts(campaignId: string, params?: { status?: string; limit?: number }) {
  return useQuery({
    queryKey: ["campaign-contacts", campaignId, params],
    queryFn: () => campaignsApi.getContacts(campaignId, params).then((r) => r.data),
    enabled: !!campaignId,
  });
}

// ── Analytics ─────────────────────────────────────────────────────────────────
export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: () => analyticsApi.dashboard().then((r) => r.data),
    staleTime: 60_000,
  });
}

// ── Folders ───────────────────────────────────────────────────────────────────
export function useFolders() {
  return useQuery({
    queryKey: ["folders"],
    queryFn: () => foldersApi.list().then((r) => r.data),
    staleTime: 30_000,
  });
}

export function useCreateFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; color?: string }) =>
      foldersApi.create(data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["folders"] }),
  });
}

export function useUpdateFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string; name?: string; color?: string }) =>
      foldersApi.update(id, data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["folders"] }),
  });
}

export function useDeleteFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => foldersApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["folders"] });
      qc.invalidateQueries({ queryKey: ["campaigns"] });
    },
  });
}

// ── Campaigns ─────────────────────────────────────────────────────────────────
export function useCampaigns(status?: string, folder_id?: string) {
  const result = useQuery({
    queryKey: ["campaigns", status, folder_id],
    queryFn: () => campaignsApi.list(status, folder_id).then((r) => r.data),
    refetchInterval: (query) => {
      const items = (query.state.data as any)?.items ?? [];
      const hasRunning = items.some((c: any) => c.status === "running");
      return hasRunning ? 5_000 : 30_000;
    },
  });
  return result;
}

export function useCampaign(id: string) {
  return useQuery({
    queryKey: ["campaigns", id],
    queryFn: () => campaignsApi.get(id).then((r) => r.data),
    enabled: !!id,
    refetchInterval: (query) => {
      const data = query.state.data as any;
      return data?.status === "running" ? 5_000 : 30_000;
    },
  });
}

export function useCreateCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CampaignCreate) => campaignsApi.create(data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campaigns"] }),
  });
}

export function useUpdateCampaign(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      campaignsApi.update(id, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      qc.invalidateQueries({ queryKey: ["campaigns", id] });
    },
  });
}

export function useDeleteCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => campaignsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campaigns"] }),
  });
}

// ── Calls ─────────────────────────────────────────────────────────────────────
export function useCalls(params?: { campaign_id?: string; outcome?: string; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ["calls", params],
    queryFn: () => callsApi.list(params).then((r) => r.data),
    refetchInterval: (query) => {
      const items = (query.state.data as any)?.items ?? [];
      // Refresh faster if any call is still pending outcome or recording
      const hasPending = items.some((c: any) => c.outcome === "pending" || !c.recording_url);
      return hasPending ? 8_000 : 30_000;
    },
  });
}

export function useCall(id: string) {
  return useQuery({
    queryKey: ["calls", id],
    queryFn: () => callsApi.get(id).then((r) => r.data),
    enabled: !!id,
    refetchInterval: (query) => {
      const data = query.state.data as any;
      // Stop polling once outcome is set and recording is available
      const settled = data && data.outcome !== "pending" && data.recording_url;
      return settled ? false : 8_000;
    },
  });
}

// ── Agents ────────────────────────────────────────────────────────────────────
export function useAgents() {
  return useQuery({
    queryKey: ["agents"],
    queryFn: () => agentsApi.list().then((r) => r.data),
  });
}

export function useAgent(id: string) {
  return useQuery({
    queryKey: ["agents", id],
    queryFn: () => agentsApi.get(id).then((r) => r.data),
    enabled: !!id,
  });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: AgentCreate) => agentsApi.create(data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

export function useUpdateAgent(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      agentsApi.update(id, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      qc.invalidateQueries({ queryKey: ["agents", id] });
    },
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => agentsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}
