import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { LibraryDefaultsTab } from "./LibraryDefaultsTab";
import type { OptionsState } from "@/features/options/useOptionsSettings";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

function makeOpts(overrides: Partial<OptionsState> = {}): OptionsState {
  return {
    settings: {
      llm: {
        baseUrl: "",
        model: "",
        provider: "openai-compatible",
        params: { temperature: 0.7, maxTokens: 512, topP: 1, frequencyPenalty: 0, presencePenalty: 0 },
        hasApiKey: false,
        apiKeyHint: null,
        authoringConcurrency: 3,
      },
      library: { defaultStorylineId: null, openLastStoryline: true },
      comfy: {
        baseUrl: "http://localhost:8199",
        workflow: "ZiT-Workflow.json",
        params: { steps: 4, cfg: 1, width: 1024, height: 1024, batchSize: 1, negativePrompt: "" },
      },
      prompts: { catalog: [], overrides: {} },
    },
    loading: false,
    error: null,
    retry: vi.fn(),
    saveLlm: vi.fn(async () => {}),
    saveLibrary: vi.fn(async () => {}),
    saveComfy: vi.fn(async () => {}),
    savePrompts: vi.fn(async () => {}),
    ...overrides,
  };
}

describe("LibraryDefaultsTab", () => {
  it("loads storylines and saves a chosen default", async () => {
    const user = userEvent.setup();
    const opts = makeOpts();
    render(<LibraryDefaultsTab opts={opts} />);

    // storyline options load asynchronously from the mocked api
    expect(await screen.findByRole("option", { name: "Embergate" })).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/default storyline/i), "Embergate");
    expect(opts.saveLibrary).toHaveBeenCalledWith(
      expect.objectContaining({ defaultStorylineId: expect.any(String) }),
    );
  });

  it("toggles the reopen-last-storyline preference", async () => {
    const user = userEvent.setup();
    const opts = makeOpts();
    render(<LibraryDefaultsTab opts={opts} />);
    await user.click(screen.getByRole("checkbox", { name: /reopen the last storyline/i }));
    expect(opts.saveLibrary).toHaveBeenCalledWith({ openLastStoryline: false });
  });
});
