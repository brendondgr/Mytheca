import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { PortraitModal } from "./PortraitModal";

import { resetArtStylesCache } from "@/hooks/use-art-styles";
import { COMFY_FIXTURE } from "@/test/api-mock";

const getSettings = vi.fn();
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getSettings: (...args: unknown[]) => getSettings(...args),
}));

beforeEach(() => {
  resetArtStylesCache();
  getSettings.mockReset();
  getSettings.mockResolvedValue({ comfy: COMFY_FIXTURE });
});

const baseProps = {
  open: true,
  onClose: () => {},
  name: "Doran Hale",
  mono: "DH",
  color: "#8E2B1C",
  portraitUrl: null,
  positive: "watercolor portrait",
  negative: "blurry",
  onPositiveChange: () => {},
  onNegativeChange: () => {},
  hasDescription: true,
  generatingPrompts: false,
  canRenderPortrait: true,
  generatingPortrait: false,
  error: null,
};

describe("PortraitModal", () => {
  it("highlights the positive prompt while it is being written", () => {
    render(
      <PortraitModal
        {...baseProps}
        onGeneratePrompts={() => {}}
        onGeneratePortrait={() => {}}
        activeField="_portraitPositive"
      />,
    );
    const positive = screen.getByLabelText(/portrait positive prompt/i);
    expect(positive.closest("label")).toHaveClass("mytheca-field-active");
  });

  it("is a dead end no longer — Try again re-runs the render after a render failure", () => {
    const onGeneratePortrait = vi.fn();
    const onGeneratePrompts = vi.fn();
    render(
      <PortraitModal
        {...baseProps}
        onGeneratePrompts={onGeneratePrompts}
        onGeneratePortrait={onGeneratePortrait}
        error="ComfyUI timed out."
      />,
    );

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("ComfyUI timed out.");

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onGeneratePortrait).toHaveBeenCalledTimes(1);
    expect(onGeneratePrompts).not.toHaveBeenCalled();
  });

  it("retries whichever generate action was attempted last (prompts)", () => {
    const onGeneratePortrait = vi.fn();
    const onGeneratePrompts = vi.fn();
    const { rerender } = render(
      <PortraitModal
        {...baseProps}
        onGeneratePrompts={onGeneratePrompts}
        onGeneratePortrait={onGeneratePortrait}
        error={null}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /generate prompts/i }));
    expect(onGeneratePrompts).toHaveBeenCalledTimes(1);

    // The prompt-generation call failed — the parent surfaces the error.
    rerender(
      <PortraitModal
        {...baseProps}
        onGeneratePrompts={onGeneratePrompts}
        onGeneratePortrait={onGeneratePortrait}
        error="Could not reach the prompt writer."
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onGeneratePrompts).toHaveBeenCalledTimes(2);
    expect(onGeneratePortrait).not.toHaveBeenCalled();
  });

  it("names the operation instead of a generic failure message", () => {
    render(
      <PortraitModal
        {...baseProps}
        onGeneratePrompts={() => {}}
        onGeneratePortrait={() => {}}
        error="Something went wrong."
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Could not render the portrait.");
  });

  describe("art style", () => {
    it("offers the picker and reports the choice", async () => {
      const user = userEvent.setup();
      const onArtStyleChange = vi.fn();
      render(
        <PortraitModal
          {...baseProps}
          onGeneratePrompts={() => {}}
          onGeneratePortrait={() => {}}
          onArtStyleChange={onArtStyleChange}
        />,
      );
      await user.click(await screen.findByRole("radio", { name: /anime/i }));
      expect(onArtStyleChange).toHaveBeenCalledWith("anime");
    });

    it("shows the chosen style selected", async () => {
      render(
        <PortraitModal
          {...baseProps}
          onGeneratePrompts={() => {}}
          onGeneratePortrait={() => {}}
          artStyle="photoreal"
          onArtStyleChange={vi.fn()}
        />,
      );
      expect(await screen.findByRole("radio", { name: /photoreal/i })).toBeChecked();
    });

    it("locks the picker while a generation is in flight", async () => {
      render(
        <PortraitModal
          {...baseProps}
          onGeneratePrompts={() => {}}
          onGeneratePortrait={() => {}}
          generatingPortrait
          onArtStyleChange={vi.fn()}
        />,
      );
      for (const radio of await screen.findAllByRole("radio")) expect(radio).toBeDisabled();
    });

    it("omits the picker entirely when no handler is wired", () => {
      render(<PortraitModal {...baseProps} onGeneratePrompts={() => {}}
          onGeneratePortrait={() => {}} />);
      expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    });
  });
});
