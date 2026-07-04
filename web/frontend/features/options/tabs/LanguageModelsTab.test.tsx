import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { LanguageModelsTab } from "./LanguageModelsTab";
import * as api from "@/lib/api";
import type { OptionsState } from "@/features/options/useOptionsSettings";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

function makeOpts(overrides: Partial<OptionsState["settings"]> = {}): OptionsState {
  return {
    settings: {
      llm: {
        baseUrl: "http://localhost:7070/v1",
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

describe("LanguageModelsTab", () => {
  it("hydrates the form from settings and saves the config", async () => {
    const user = userEvent.setup();
    const opts = makeOpts();
    render(<LanguageModelsTab opts={opts} />);

    const baseUrl = screen.getByLabelText(/base url/i) as HTMLInputElement;
    expect(baseUrl.value).toBe("http://localhost:7070/v1");

    await user.type(screen.getByLabelText(/^model$/i), "llama-3.1-8b");
    await user.click(screen.getByRole("button", { name: /save/i }));

    expect(opts.saveLlm).toHaveBeenCalledWith(
      expect.objectContaining({
        baseUrl: "http://localhost:7070/v1",
        model: "llama-3.1-8b",
      }),
    );
    expect(await screen.findByText(/saved/i)).toBeInTheDocument();
  });

  it("hydrates and saves the authoring concurrency", async () => {
    const user = userEvent.setup();
    const opts = makeOpts();
    render(<LanguageModelsTab opts={opts} />);

    const field = screen.getByLabelText(/max parallel authoring requests/i) as HTMLInputElement;
    expect(field.value).toBe("3");
    fireEvent.change(field, { target: { value: "6" } });
    await user.click(screen.getByRole("button", { name: /save/i }));
    expect(opts.saveLlm).toHaveBeenCalledWith(
      expect.objectContaining({ authoringConcurrency: 6 }),
    );
  });

  it("omits the apiKey when the field is left blank (keeps the stored key)", async () => {
    const user = userEvent.setup();
    const opts = makeOpts({
      llm: {
        baseUrl: "http://localhost:7070/v1",
        model: "m1",
        provider: "openai-compatible",
        params: { temperature: 0.7, maxTokens: 512, topP: 1, frequencyPenalty: 0, presencePenalty: 0 },
        hasApiKey: true,
        apiKeyHint: "…AB12",
        authoringConcurrency: 3,
      },
    });
    render(<LanguageModelsTab opts={opts} />);
    await user.click(screen.getByRole("button", { name: /save/i }));
    const call = (opts.saveLlm as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(call).not.toHaveProperty("apiKey");
  });

  it("fetches models into a dropdown, then saves the chosen model", async () => {
    const user = userEvent.setup();
    const opts = makeOpts();
    render(<LanguageModelsTab opts={opts} />);

    await user.click(screen.getByRole("button", { name: /fetch models/i }));
    // The model control becomes a <select> populated from the fetch.
    expect(await screen.findByRole("option", { name: "llama-3.1-8b" })).toBeInTheDocument();
    expect(screen.getByText(/2 available/i)).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/^model/i), "qwen2.5");
    await user.click(screen.getByRole("button", { name: /save/i }));
    expect(opts.saveLlm).toHaveBeenCalledWith(
      expect.objectContaining({ model: "qwen2.5" }),
    );
  });

  it("runs a connection test and shows the result", async () => {
    const user = userEvent.setup();
    const opts = makeOpts({
      llm: {
        baseUrl: "http://localhost:7070/v1",
        model: "llama-3.1-8b",
        provider: "openai-compatible",
        params: { temperature: 0.7, maxTokens: 512, topP: 1, frequencyPenalty: 0, presencePenalty: 0 },
        hasApiKey: false,
        apiKeyHint: null,
        authoringConcurrency: 3,
      },
    });
    render(<LanguageModelsTab opts={opts} />);
    await user.click(screen.getByRole("button", { name: /test connection/i }));
    expect(await screen.findByText(/OK · 42ms/i)).toBeInTheDocument();
  });

  it("surfaces a fetch error and leaves the model as a text field", async () => {
    const user = userEvent.setup();
    vi.mocked(api.fetchLlmModels).mockRejectedValueOnce(new Error("Could not reach the model endpoint."));
    const opts = makeOpts();
    render(<LanguageModelsTab opts={opts} />);

    await user.click(screen.getByRole("button", { name: /fetch models/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not reach/i);
    // No options rendered; the model control stays a plain text input.
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
  });
});
