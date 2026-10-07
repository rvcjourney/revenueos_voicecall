import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { agentsApi } from "@/lib/api";
import type { AgentTemplate, SipTrunk, SipTransport } from "@/lib/types";
import { TestCallDialog } from "./Agents";

vi.mock("@/lib/hooks", () => ({
  useMyTrunks: () => ({
    data: [
      {
        id: "trunk-1",
        name: "Main line",
        livekit_trunk_id: "ST_abc",
        sip_domain: "abc.sip.vobiz.ai",
        sip_username: "abc",
        caller_id: "+912212345678",
        transport: "tcp" as SipTransport,
        is_default: true,
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
        inbound_enabled: false,
        inbound_agent_template_id: null,
      } satisfies SipTrunk,
    ],
    isLoading: false,
  }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    agentsApi: { ...actual.agentsApi, testCall: vi.fn() },
  };
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const agent: AgentTemplate = {
  id: "agent-1",
  name: "Sales Bot",
  description: null,
  language: "hinglish",
  welcome_message: "Namaste!",
  system_prompt: "Be helpful.",
  voice_id: "voice-1",
  voice_provider: "elevenlabs",
  llm_model: "qwen/qwen3.8-27b",
  llm_temperature: 0.7,
  max_call_duration_seconds: 600,
  created_at: "2026-01-01T00:00:00Z",
  access_status: "approved",
  access_request_id: null,
  can_edit: true,
};

function renderDialog(onOpenChange = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TestCallDialog agent={agent} onOpenChange={onOpenChange} />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("TestCallDialog", () => {
  it("shows the backend's rate-limit message inline, not a raw/blank failure", async () => {
    const user = userEvent.setup();
    vi.mocked(agentsApi.testCall).mockRejectedValueOnce({
      isAxiosError: true,
      response: {
        status: 429,
        data: {
          detail: "Test call limit reached: 3 per hour. Try again in 42 minute(s).",
          code: "RATE_LIMITED",
          retry_after_seconds: 2520,
        },
      },
    });

    renderDialog();

    await user.click(screen.getByRole("button", { name: /place test call/i }));

    expect(
      await screen.findByText("Test call limit reached: 3 per hour. Try again in 42 minute(s).")
    ).toBeInTheDocument();
  });

  it("shows a fallback message for an error with no backend detail", async () => {
    const user = userEvent.setup();
    vi.mocked(agentsApi.testCall).mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 500, data: {} },
    });

    renderDialog();
    await user.click(screen.getByRole("button", { name: /place test call/i }));

    expect(await screen.findByText("Couldn't start test call")).toBeInTheDocument();
  });

  it("closes the dialog and does not show an error on success", async () => {
    const user = userEvent.setup();
    vi.mocked(agentsApi.testCall).mockResolvedValueOnce({
      data: { call_id: "call-1", status: "initiated" },
    } as Awaited<ReturnType<typeof agentsApi.testCall>>);
    const onOpenChange = vi.fn();

    renderDialog(onOpenChange);
    await user.click(screen.getByRole("button", { name: /place test call/i }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalled());
    expect(screen.queryByText(/couldn't start test call/i)).not.toBeInTheDocument();
  });
});
