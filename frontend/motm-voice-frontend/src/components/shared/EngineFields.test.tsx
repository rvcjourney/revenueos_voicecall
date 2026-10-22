import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EngineSelect, IndicNativeVoiceSelect, engineSwitchPatch } from "./EngineFields";

const state = vi.hoisted(() => ({
  engines: [{ value: "standard", label: "Standard" }] as { value: string; label: string }[],
}));

vi.mock("@/lib/hooks", () => ({
  useEngines: () => ({ data: { engines: state.engines, default_pipeline: "standard", cloning_allowed: true } }),
  useLanguages: () => ({
    data: [{ value: "tamil", label: "Tamil", native: "தமிழ்", cloned_voices: true, voices: [
      { id: "ritu", name: "Ritu", gender: "female" },
      { id: "shubh", name: "Shubh", gender: "male" },
    ] }],
    isLoading: false,
  }),
  useClonedVoices: () => ({
    data: [
      { id: "1", name: "Mine (Indic)", elevenlabs_voice_id: "svc-1", status: "ready", engine: "sarvam", created_at: "" },
      { id: "2", name: "Mine (Standard)", elevenlabs_voice_id: "el-2", status: "ready", engine: "standard", created_at: "" },
    ],
  }),
}));

describe("engine fields", () => {
  it("switching engine always clears the voice and sets the matching provider", () => {
    expect(engineSwitchPatch("sarvam")).toEqual({ pipeline: "sarvam", voice_id: "", voice_provider: "sarvam" });
    expect(engineSwitchPatch("standard")).toEqual({ pipeline: "standard", voice_id: "", voice_provider: "elevenlabs" });
  });

  it("hides the engine picker when only Standard is enabled", () => {
    state.engines = [{ value: "standard", label: "Standard" }];
    const { container } = render(<EngineSelect value="standard" onChange={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows neutral labels when Indic Native is enabled", () => {
    state.engines = [{ value: "standard", label: "Standard" }, { value: "sarvam", label: "Indic Native" }];
    render(<EngineSelect value="sarvam" onChange={() => {}} />);
    expect(screen.getByText("Calling engine")).toBeInTheDocument();
    expect(screen.getByText("Indic Native")).toBeInTheDocument();
    expect(document.body.textContent?.toLowerCase()).not.toContain("sarvam");
  });

  it("offers this language's stock voices plus only Indic Native cloned voices", () => {
    render(<IndicNativeVoiceSelect language="tamil" value="svc-1" onChange={() => {}} />);
    expect(screen.getByText("Mine (Indic)")).toBeInTheDocument();
    expect(screen.queryByText("Mine (Standard)")).not.toBeInTheDocument();
  });
});
