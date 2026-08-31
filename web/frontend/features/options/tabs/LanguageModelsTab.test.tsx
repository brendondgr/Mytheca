import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { LanguageModelsTab } from "./LanguageModelsTab";
import * as api from "@/lib/api";
import type { OptionsState } from "@/features/options/useOptionsSettings";
import { COMFY_FIXTURE } from "@/test/api-mock";

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
        maxContextTokens: 16384,
        reasoningVisibility: "summary" as const,
        providers: [
          { id: "openai-compatible", label: "OpenAI-compatible", configured: true, defaultBaseUrl: "", supportsDiscovery: true, streamingDispatched: true },
          { id: "anthropic", label: "Anthropic (Claude)", configured: false, defaultBaseUrl: "https://api.anthropic.com", supportsDiscovery: true, streamingDispatched: true },
        ],
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
    // Match the status region exactly — /saved/i alone also hits body copy on the page.
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
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
        maxContextTokens: 16384,
        reasoningVisibility: "summary" as const,
        providers: [
          { id: "openai-compatible", label: "OpenAI-compatible", configured: true, defaultBaseUrl: "", supportsDiscovery: true, streamingDispatched: true },
          { id: "anthropic", label: "Anthropic (Claude)", configured: false, defaultBaseUrl: "https://api.anthropic.com", supportsDiscovery: true, streamingDispatched: true },
        ],
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
        maxContextTokens: 16384,
        reasoningVisibility: "summary" as const,
        providers: [
          { id: "openai-compatible", label: "OpenAI-compatible", configured: true, defaultBaseUrl: "", supportsDiscovery: true, streamingDispatched: true },
          { id: "anthropic", label: "Anthropic (Claude)", configured: false, defaultBaseUrl: "https://api.anthropic.com", supportsDiscovery: true, streamingDispatched: true },
        ],
      },
    });
    render(<LanguageModelsTab opts={opts} />);
    await user.click(screen.getByRole("button", { name: /test connection/i }));
    expect(await screen.findByText(/OK · 42ms/i)).toBeInTheDocument();
  });

  it("hydrates and saves the max context tokens", async () => {
    const user = userEvent.setup();
    const opts = makeOpts();
    render(<LanguageModelsTab opts={opts} />);

    const field = screen.getByLabelText(/max context \(tokens\)/i) as HTMLInputElement;
    expect(field.value).toBe("16384");
    fireEvent.change(field, { target: { value: "32768" } });
    await user.click(screen.getByRole("button", { name: /save/i }));
    expect(opts.saveLlm).toHaveBeenCalledWith(
      expect.objectContaining({ maxContextTokens: 32768 }),
    );
  });

  it("surfaces a fetch error and leaves the model as a text field", async () => {
    const user = userEvent.setup();
    vi.mocked(api.fetchLlmModels).mockRejectedValueOnce(new Error("Could not reach the model endpoint."));
    const opts = makeOpts();
    render(<LanguageModelsTab opts={opts} />);

    await user.click(screen.getByRole("button", { name: /fetch models/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not reach/i);
    // The MODEL control stays a plain text input. Scoped to it on purpose: the
    // provider picker is also a <select>, so an unscoped queryByRole("option")
    // now finds its entries and would pass whatever the model control did.
    expect(screen.getByLabelText(/^model/i)).toHaveProperty("tagName", "INPUT");
  });

  it("tells the three empty states apart", async () => {
    const user = userEvent.setup();
    const opts = makeOpts();

    // Unreachable — the route answers 200 with ok:false, not a throw.
    vi.mocked(api.fetchLlmModels).mockResolvedValueOnce({
      models: [], ok: false, error: "connection refused", source: "none",
    });
    const view = render(<LanguageModelsTab opts={opts} />);
    await user.click(screen.getByRole("button", { name: /fetch models/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/simply be off/i);
    view.unmount();

    // Reached, and serving nothing — a different sentence, and not an alert.
    vi.mocked(api.fetchLlmModels).mockResolvedValueOnce({
      models: [], ok: true, error: null, source: "endpoint",
    });
    render(<LanguageModelsTab opts={opts} />);
    await user.click(screen.getByRole("button", { name: /fetch models/i }));
    expect(await screen.findByText(/reports no models/i)).toBeInTheDocument();
  });

  it("says when a provider's turns will not type out", async () => {
    const user = userEvent.setup();
    const opts = makeOpts();
    // Anthropic's stream is not parsed by the turn loop yet. Selecting it works,
    // but every turn arrives as one block — which the picker must say, because
    // the alternative is an operator discovering it mid-scene with no error.
    opts.settings!.llm.providers = opts.settings!.llm.providers.map((p) =>
      p.id === "anthropic" ? { ...p, streamingDispatched: false } : p,
    );
    render(<LanguageModelsTab opts={opts} />);
    await user.selectOptions(screen.getByLabelText(/provider/i), "anthropic");
    expect(screen.getByText(/arrive as one block/i)).toBeInTheDocument();
  });

  it("keeps each provider's endpoint and key separate when switching", async () => {
    const user = userEvent.setup();
    render(<LanguageModelsTab opts={makeOpts()} />);

    await user.selectOptions(screen.getByLabelText(/provider/i), "anthropic");
    // Stale models from the previous provider must not survive the switch —
    // offering an Ollama tag as an Anthropic model is worse than offering none.
    expect(screen.getByLabelText(/^model/i)).toHaveValue("");
  });
});
