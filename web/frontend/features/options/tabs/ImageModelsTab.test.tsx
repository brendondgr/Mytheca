import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ImageModelsTab } from "./ImageModelsTab";
import * as api from "@/lib/api";
import type { OptionsState } from "@/features/options/useOptionsSettings";
import { COMFY_FIXTURE } from "@/test/api-mock";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

function makeOpts(overrides: Partial<OptionsState["settings"]> = {}): OptionsState {
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
        maxContextTokens: 16384,
        reasoningVisibility: "summary" as const,
      },
      library: { defaultStorylineId: null, openLastStoryline: true },
      comfy: COMFY_FIXTURE,
      prompts: { catalog: [], overrides: {} },
      ...overrides,
    },
    loading: false,
    error: null,
    retry: vi.fn(),
    saveLlm: vi.fn(async () => {}),
    saveLibrary: vi.fn(async () => {}),
    saveComfy: vi.fn(async () => {}),
    savePrompts: vi.fn(async () => {}),
  };
}

describe("ImageModelsTab", () => {
  it("hydrates from settings and saves the config", async () => {
    const user = userEvent.setup();
    const opts = makeOpts();
    render(<ImageModelsTab opts={opts} />);

    const baseUrl = screen.getByLabelText(/comfyui base url/i) as HTMLInputElement;
    expect(baseUrl.value).toBe("http://localhost:8199");

    await user.click(screen.getByRole("button", { name: /^save$/i }));
    expect(opts.saveComfy).toHaveBeenCalledWith(
      expect.objectContaining({
        baseUrl: "http://localhost:8199",
        workflow: "ZiT-Workflow.json",
      }),
    );
    expect(await screen.findByText(/saved/i)).toBeInTheDocument();
  });

  it("lists workflows into a dropdown, then saves the chosen workflow", async () => {
    const user = userEvent.setup();
    const opts = makeOpts();
    render(<ImageModelsTab opts={opts} />);

    await user.click(screen.getByRole("button", { name: /list workflows/i }));
    expect(await screen.findByRole("option", { name: "Other.json" })).toBeInTheDocument();
    expect(screen.getByText(/2 available/i)).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/^workflow/i), "Other.json");
    await user.click(screen.getByRole("button", { name: /^save$/i }));
    expect(opts.saveComfy).toHaveBeenCalledWith(
      expect.objectContaining({ workflow: "Other.json" }),
    );
  });

  it("runs a status check and shows the server version", async () => {
    const user = userEvent.setup();
    const opts = makeOpts();
    render(<ImageModelsTab opts={opts} />);
    await user.click(screen.getByRole("button", { name: /check status/i }));
    expect(await screen.findByText(/OK · v0\.25\.0/i)).toBeInTheDocument();
  });

  it("surfaces a status error", async () => {
    const user = userEvent.setup();
    vi.mocked(api.checkComfyStatus).mockRejectedValueOnce(new Error("Could not reach ComfyUI."));
    const opts = makeOpts();
    render(<ImageModelsTab opts={opts} />);
    await user.click(screen.getByRole("button", { name: /check status/i }));
    expect(await screen.findByText(/could not reach comfyui/i)).toBeInTheDocument();
  });
});
