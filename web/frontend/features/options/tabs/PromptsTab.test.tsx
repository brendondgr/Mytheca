import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { PromptsTab } from "./PromptsTab";
import type { OptionsState } from "@/features/options/useOptionsSettings";
import type { PromptSpec } from "@/lib/api";

const CATALOG: PromptSpec[] = [
  {
    key: "narrator.system",
    agent: "Narrator",
    label: "Transition beat",
    description: "Short narration between beats.",
    default: "DEF NARR",
  },
];

function makeOpts(overrides: Record<string, string>, savePrompts = vi.fn(async () => {})): OptionsState {
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
        baseUrl: "",
        workflow: "ZiT-Workflow.json",
        params: { steps: 4, cfg: 1, width: 1024, height: 1024, batchSize: 1, negativePrompt: "" },
      },
      prompts: { catalog: CATALOG, overrides },
    },
    loading: false,
    error: null,
    retry: vi.fn(),
    saveLlm: vi.fn(async () => {}),
    saveLibrary: vi.fn(async () => {}),
    saveComfy: vi.fn(async () => {}),
    savePrompts,
  };
}

describe("PromptsTab", () => {
  it("renders the writing-agent sub-tabs from the catalog", () => {
    render(<PromptsTab opts={makeOpts({})} />);
    expect(screen.getByRole("tab", { name: "Narrator" })).toBeInTheDocument();
  });

  it("saves a new global override", async () => {
    const user = userEvent.setup();
    const savePrompts = vi.fn(async () => {});
    render(<PromptsTab opts={makeOpts({}, savePrompts)} />);
    const field = screen.getByRole("textbox", { name: /narrator — transition beat prompt/i });
    await user.clear(field);
    await user.type(field, "GLOBAL NARR");
    await user.click(screen.getByRole("button", { name: /save global prompts/i }));
    expect(savePrompts).toHaveBeenCalledWith({ overrides: { "narrator.system": "GLOBAL NARR" } });
  });

  it("clears a removed override with a blank merge patch", async () => {
    const user = userEvent.setup();
    const savePrompts = vi.fn(async () => {});
    render(<PromptsTab opts={makeOpts({ "narrator.system": "OLD" }, savePrompts)} />);
    await user.click(screen.getByRole("button", { name: /reset to default/i }));
    await user.click(screen.getByRole("button", { name: /save global prompts/i }));
    // The removed key is sent blank so the global namespace clears it.
    expect(savePrompts).toHaveBeenCalledWith({ overrides: { "narrator.system": "" } });
  });
});
