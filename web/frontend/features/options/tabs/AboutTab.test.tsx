import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { AboutTab } from "./AboutTab";
import * as api from "@/lib/api";
import type { OptionsState } from "@/features/options/useOptionsSettings";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

function makeOpts(overrides: Partial<OptionsState> = {}): OptionsState {
  return {
    settings: {
      llm: {
        baseUrl: "http://localhost:7070/v1",
        model: "llama-3.1-8b",
        provider: "openai-compatible",
        params: { temperature: 0.7, maxTokens: 512, topP: 1, frequencyPenalty: 0, presencePenalty: 0 },
        hasApiKey: false,
        apiKeyHint: null,
      },
      library: { defaultStorylineId: null, openLastStoryline: true },
      comfy: {
        baseUrl: "http://localhost:8199",
        workflow: "ZiT-Workflow.json",
        params: { steps: 4, cfg: 1, width: 1024, height: 1024, batchSize: 1, negativePrompt: "" },
      },
    },
    loading: false,
    error: null,
    retry: vi.fn(),
    saveLlm: vi.fn(async () => {}),
    saveLibrary: vi.fn(async () => {}),
    saveComfy: vi.fn(async () => {}),
    ...overrides,
  };
}

describe("AboutTab", () => {
  it("renders the detected inference engine and budget ladder from the mock", async () => {
    render(<AboutTab opts={makeOpts()} />);

    // Engine row: mock returns backend="vllm", displayed as "vLLM"
    expect(await screen.findByText("vLLM")).toBeInTheDocument();

    // At least one budget value from the mock payload is rendered
    // mock returns low=256, medium=512, high=1024, very_high=2048, max=4096
    expect(await screen.findByText("4,096")).toBeInTheDocument();

    // The budget ladder label is present
    expect(screen.getByRole("list", { name: /reasoning budget ladder/i })).toBeInTheDocument();
  });

  it("shows 'unavailable' for the inference engine when getLlmBackend rejects", async () => {
    vi.mocked(api.getLlmBackend).mockRejectedValueOnce(new Error("network error"));

    render(<AboutTab opts={makeOpts()} />);

    expect(await screen.findByText("unavailable")).toBeInTheDocument();
    // Budget ladder is not rendered when data is unavailable
    expect(screen.queryByRole("list", { name: /reasoning budget ladder/i })).not.toBeInTheDocument();
  });
});
