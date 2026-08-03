import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  adminApi,
  agentsApi,
  analyticsApi,
  authApi,
  billingApi,
  callsApi,
  campaignsApi,
  foldersApi,
  inboundAgentsApi,
  plansApi,
  sipTrunksApi,
  unwrapList,
  usageApi,
  voiceCloningApi,
} from "./api";
import type { AgentCreate, CampaignCreate, InboundAgentCreate } from "./types";

// ── Dashboard / analytics / usage ───────────────────────────────────────
export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: () => analyticsApi.dashboard().then((r) => r.data),
    refetchInterval: 30_000,
  });
}

export function useOrgInfo() {
  return useQuery({ queryKey: ["org-info"], queryFn: () => authApi.orgInfo().then((r) => r.data) });
}

export function useConcurrency() {
  return useQuery({
    queryKey: ["concurrency"],
    queryFn: () => usageApi.concurrency().then((r) => r.data),
    refetchInterval: 15_000,
  });
}

export function useCreditUsage() {
  return useQuery({ queryKey: ["credit-usage"], queryFn: () => usageApi.credits().then((r) => r.data) });
}

// ── Pricing & billing ────────────────────────────────────────────────────
export function usePublicPlans() {
  return useQuery({ queryKey: ["public-plans"], queryFn: () => plansApi.list().then((r) => r.data) });
}

export function useBillingCurrent() {
  return useQuery({ queryKey: ["billing-current"], queryFn: () => billingApi.current().then((r) => r.data) });
}

export function useCheckout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => billingApi.checkout(planId).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["billing-current"] }),
  });
}

export function useVerifyPayment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { razorpay_payment_id: string; razorpay_subscription_id: string; razorpay_signature: string }) =>
      billingApi.verifyPayment(data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["billing-current"] }),
  });
}

export function useCancelSubscription() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => billingApi.cancel().then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["billing-current"] }),
  });
}

// ── Folders ──────────────────────────────────────────────────────────────
export function useFolders() {
  return useQuery({
    queryKey: ["folders"],
    queryFn: () => foldersApi.list().then((r) => unwrapList(r.data)),
  });
}

export function useCreateFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; color?: string }) => foldersApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["folders"] }),
  });
}

// ── Campaigns ────────────────────────────────────────────────────────────
export function useCampaigns(params?: { status?: string; folder_id?: string }) {
  return useQuery({
    queryKey: ["campaigns", params],
    queryFn: () => campaignsApi.list(params).then((r) => unwrapList(r.data)),
    refetchInterval: 20_000,
  });
}

export function useCampaign(id: string | undefined) {
  return useQuery({
    queryKey: ["campaign", id],
    queryFn: () => campaignsApi.get(id!).then((r) => r.data),
    enabled: !!id,
    refetchInterval: (query) => (query.state.data?.status === "running" ? 5_000 : 20_000),
  });
}

export function useCampaignContacts(id: string | undefined, params?: { status?: string; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ["campaign-contacts", id, params],
    queryFn: () => campaignsApi.contacts(id!, params).then((r) => r.data),
    enabled: !!id,
  });
}

export function useCreateCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CampaignCreate) => campaignsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campaigns"] }),
  });
}

export function useUpdateCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) => campaignsApi.update(id, data),
    onSuccess: (_r, vars) => {
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      qc.invalidateQueries({ queryKey: ["campaign", vars.id] });
    },
  });
}

export function useLaunchCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => campaignsApi.launch(id),
    onSuccess: (_r, id) => {
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      qc.invalidateQueries({ queryKey: ["campaign", id] });
    },
  });
}

export function usePauseCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => campaignsApi.pause(id),
    onSuccess: (_r, id) => {
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      qc.invalidateQueries({ queryKey: ["campaign", id] });
    },
  });
}

export function useDuplicateCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => campaignsApi.duplicate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campaigns"] }),
  });
}

export function useUploadContacts() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => campaignsApi.uploadContacts(id, file),
    onSuccess: (_r, vars) => {
      qc.invalidateQueries({ queryKey: ["campaign", vars.id] });
      qc.invalidateQueries({ queryKey: ["campaign-contacts", vars.id] });
    },
  });
}

// ── Calls ────────────────────────────────────────────────────────────────
export function useCalls(params?: { campaign_id?: string; outcome?: string; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ["calls", params],
    queryFn: () => callsApi.list(params).then((r) => unwrapList(r.data)),
    refetchInterval: 15_000,
  });
}

export function useCall(id: string | undefined) {
  return useQuery({
    queryKey: ["call", id],
    queryFn: () => callsApi.get(id!).then((r) => r.data),
    enabled: !!id,
  });
}

export function useFetchRecording() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => callsApi.fetchRecording(id),
    onSuccess: (_r, id) => qc.invalidateQueries({ queryKey: ["call", id] }),
  });
}

// ── Agents ───────────────────────────────────────────────────────────────
export function useAgents() {
  return useQuery({
    queryKey: ["agents"],
    queryFn: () => agentsApi.list().then((r) => unwrapList(r.data)),
    refetchInterval: 20_000,
    refetchOnWindowFocus: true,
  });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: AgentCreate) => agentsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

export function useUpdateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<AgentCreate> }) => agentsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => agentsApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

export function useRequestAgentAccess() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => agentsApi.requestAccess(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

// ── Inbound agents ─────────────────────────────────────────────────────────
export function useInboundAgents() {
  return useQuery({
    queryKey: ["inbound-agents"],
    queryFn: () => inboundAgentsApi.list().then((r) => unwrapList(r.data)),
  });
}

export function useCreateInboundAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: InboundAgentCreate) => inboundAgentsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inbound-agents"] }),
  });
}

export function useUpdateInboundAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<InboundAgentCreate> }) => inboundAgentsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inbound-agents"] }),
  });
}

export function useDeleteInboundAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => inboundAgentsApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inbound-agents"] }),
  });
}

// ── Voice cloning ────────────────────────────────────────────────────────
export function useClonedVoices() {
  return useQuery({
    queryKey: ["cloned-voices"],
    queryFn: () => voiceCloningApi.list().then((r) => unwrapList(r.data)),
  });
}

export function useCreateClonedVoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; file: File; consentVideo: File }) => voiceCloningApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cloned-voices"] }),
  });
}

export function useDeleteClonedVoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => voiceCloningApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cloned-voices"] }),
  });
}

// ── SIP trunks ───────────────────────────────────────────────────────────
export function useSipTrunks() {
  return useQuery({
    queryKey: ["sip-trunks"],
    queryFn: () => sipTrunksApi.list().then((r) => unwrapList(r.data)),
  });
}

export function useMyTrunks() {
  return useQuery({
    queryKey: ["my-trunks"],
    queryFn: () => sipTrunksApi.my().then((r) => unwrapList(r.data)),
  });
}

export function useTrunkAssignments(id: string | undefined) {
  return useQuery({
    queryKey: ["trunk-assignments", id],
    queryFn: () => sipTrunksApi.assignments(id!).then((r) => r.data),
    enabled: !!id,
  });
}

export function useSetupInboundCalling() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ trunkId, agentId }: { trunkId: string; agentId: string }) =>
      sipTrunksApi.setupInbound(trunkId, agentId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sip-trunks"] }),
  });
}

export function useUpdateInboundCallingAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ trunkId, agentId }: { trunkId: string; agentId: string }) =>
      sipTrunksApi.updateInboundAgent(trunkId, agentId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sip-trunks"] }),
  });
}

export function useDisableInboundCalling() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (trunkId: string) => sipTrunksApi.disableInbound(trunkId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sip-trunks"] }),
  });
}

// ── Admin ────────────────────────────────────────────────────────────────
export function useAdminOrg() {
  return useQuery({ queryKey: ["admin-org"], queryFn: () => adminApi.org().then((r) => r.data) });
}

export function useAdminStats() {
  return useQuery({ queryKey: ["admin-stats"], queryFn: () => adminApi.stats().then((r) => r.data) });
}

export function useAdminUsers() {
  return useQuery({ queryKey: ["admin-users"], queryFn: () => adminApi.users().then((r) => r.data) });
}

export function useAgentRequests(status?: string) {
  return useQuery({
    queryKey: ["agent-requests", status],
    queryFn: () => adminApi.agentRequests(status).then((r) => r.data),
    refetchInterval: 20_000,
  });
}

export function useAgentAccessList() {
  return useQuery({
    queryKey: ["agent-access"],
    queryFn: () => adminApi.agentAccess().then((r) => r.data),
    refetchInterval: 20_000,
  });
}

export function useAgentCreationRequestsAdmin(status?: string) {
  return useQuery({
    queryKey: ["agent-creation-requests-admin", status],
    queryFn: () => adminApi.agentCreationRequests(status).then((r) => r.data),
  });
}

export function useActivity() {
  return useQuery({ queryKey: ["activity"], queryFn: () => adminApi.activity().then((r) => r.data) });
}

export function useDncList(q?: string) {
  return useQuery({ queryKey: ["dnc", q], queryFn: () => adminApi.dnc(q).then((r) => r.data) });
}
