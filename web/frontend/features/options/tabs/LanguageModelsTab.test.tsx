import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { LanguageModelsTab } from "./LanguageModelsTab";
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
      },
      library: { defaultStorylineId: null, openLastStoryline: true },
      ...overrides,
    },
    loading: false,
    error: null,
    retry: vi.fn(),
    saveLlm: vi.fn(async () => {}),
    saveLibrary: vi.fn(async () => {}),
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
      },
    });
    render(<LanguageModelsTab opts={opts} />);
    await user.click(screen.getByRole("button", { name: /save/i }));
    const call = (opts.saveLlm as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(call).not.toHaveProperty("apiKey");
  });
});
