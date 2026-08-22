import { render, screen, within } from "@testing-library/react";
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

  describe("art style", () => {
    it("shows the three styles with the stored default selected", async () => {
      render(<ImageModelsTab opts={makeOpts()} />);
      const group = screen.getByRole("group", { name: /^art style$/i });
      const radios = within(group).getAllByRole("radio");
      expect(radios).toHaveLength(3);
      expect(within(group).getByRole("radio", { name: /painted/i })).toBeChecked();
    });

    it("saves a new default style", async () => {
      const user = userEvent.setup();
      const state = makeOpts();
      render(<ImageModelsTab opts={state} />);

      const group = screen.getByRole("group", { name: /^art style$/i });
      await user.click(within(group).getByRole("radio", { name: /photoreal/i }));
      await user.click(screen.getByRole("button", { name: /^save$/i }));

      expect(state.saveComfy).toHaveBeenCalledWith(
        expect.objectContaining({ artStyle: "photoreal" }),
      );
    });

    it("saves each style's LoRA file, strength and on/off", async () => {
      const user = userEvent.setup();
      const state = makeOpts();
      render(<ImageModelsTab opts={state} />);

      // Turning painted's LoRA off is how you render the house style on the base model.
      await user.click(screen.getByRole("checkbox", { name: /use a lora for painted/i }));
      await user.click(screen.getByRole("button", { name: /^save$/i }));

      expect(state.saveComfy).toHaveBeenCalledWith(
        expect.objectContaining({
          styles: expect.objectContaining({
            painted: expect.objectContaining({
              loraEnabled: false,
              loraName: "zit_watercolor.safetensors",
            }),
          }),
        }),
      );
    });

    it("keeps the LoRA field usable as free text when ComfyUI is unreachable", () => {
      render(<ImageModelsTab opts={makeOpts()} />);
      // Anime ships with no LoRA and nothing has been listed, so it is a plain input the
      // operator can type into rather than an empty, unusable select.
      expect(screen.getByLabelText(/anime lora file/i)).toHaveAttribute("placeholder");
    });

    it("offers the server's LoRAs as a dropdown once listed", async () => {
      const user = userEvent.setup();
      render(<ImageModelsTab opts={makeOpts()} />);

      await user.click(screen.getByRole("button", { name: /list loras/i }));
      const select = await screen.findByLabelText(/anime lora file/i);
      expect(select.tagName).toBe("SELECT");
      expect(
        within(select as HTMLSelectElement).getByRole("option", {
          name: "zit_oilpainting.safetensors",
        }),
      ).toBeInTheDocument();
    });
  });
});
