import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

describe("AboutTab — Maintenance section", () => {
  it("renders the Scan button initially", () => {
    render(<AboutTab opts={makeOpts()} />);
    expect(
      screen.getByRole("button", { name: /scan for orphaned media/i }),
    ).toBeInTheDocument();
  });

  it("shows orphan count and eligible count after a successful scan", async () => {
    const user = userEvent.setup();
    render(<AboutTab opts={makeOpts()} />);

    await user.click(screen.getByRole("button", { name: /scan for orphaned media/i }));

    // The "Delete N files" button appears — mock returns eligibleCount=3
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /delete 3 files/i }),
      ).toBeInTheDocument();
    });

    // aria-live region is populated with orphan count
    expect(screen.getByRole("status")).toHaveTextContent(/4 orphans found/i);
  });

  it("shows confirmation step on first delete click, then calls cleanup on confirm", async () => {
    const user = userEvent.setup();
    render(<AboutTab opts={makeOpts()} />);

    // Scan first
    await user.click(screen.getByRole("button", { name: /scan for orphaned media/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /delete 3 files/i })).toBeInTheDocument(),
    );

    // Click the delete button — should show confirmation, not immediately delete
    await user.click(screen.getByRole("button", { name: /delete 3 files/i }));
    expect(screen.getByText(/are you sure\?/i)).toBeInTheDocument();
    expect(vi.mocked(api.cleanupMediaOrphans)).not.toHaveBeenCalled();

    // Click Cancel — confirmation disappears
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByText(/are you sure\?/i)).not.toBeInTheDocument();

    // Click delete again then confirm
    await user.click(screen.getByRole("button", { name: /delete 3 files/i }));
    await user.click(screen.getByRole("button", { name: /yes, delete/i }));

    expect(vi.mocked(api.cleanupMediaOrphans)).toHaveBeenCalledOnce();

    // After cleanup, the aria-live region announces the result
    // mock returns deletedCount=3, freedBytes=30720
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(/deleted 3 files/i);
    });
  });

  it("shows an error message when the scan fails", async () => {
    vi.mocked(api.getMediaOrphans).mockRejectedValueOnce(new Error("network"));
    const user = userEvent.setup();
    render(<AboutTab opts={makeOpts()} />);

    await user.click(screen.getByRole("button", { name: /scan for orphaned media/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/scan failed/i);
  });
});
