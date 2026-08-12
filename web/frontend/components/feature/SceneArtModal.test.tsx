import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { SceneArtModal } from "./SceneArtModal";

const baseProps = {
  open: true,
  onClose: () => {},
  name: "The Quay",
  imageUrl: null,
  positive: "watercolor harbor",
  negative: "people",
  onPositiveChange: () => {},
  onNegativeChange: () => {},
  hasDescription: true,
  generatingPrompts: false,
  onGeneratePrompts: () => {},
  canRender: true,
  generatingImage: false,
  onGenerate: () => {},
  error: null,
};

describe("SceneArtModal", () => {
  it("highlights the positive prompt while it is being written", () => {
    render(<SceneArtModal {...baseProps} activeField="_sceneArtPositive" />);
    const positive = screen.getByLabelText(/scene-art positive prompt/i);
    const negative = screen.getByLabelText(/scene-art negative prompt/i);
    expect(positive.closest("label")).toHaveClass("mytheca-field-active");
    expect(negative.closest("label")).not.toHaveClass("mytheca-field-active");
  });

  it("highlights the negative prompt when it is the active field", () => {
    render(<SceneArtModal {...baseProps} activeField="_sceneArtNegative" />);
    expect(
      screen.getByLabelText(/scene-art negative prompt/i).closest("label"),
    ).toHaveClass("mytheca-field-active");
  });

  it("highlights nothing when no field is active", () => {
    render(<SceneArtModal {...baseProps} activeField={null} />);
    expect(
      screen.getByLabelText(/scene-art positive prompt/i).closest("label"),
    ).not.toHaveClass("mytheca-field-active");
  });

  it("is a dead end no longer — Try again re-runs the render after a render failure", () => {
    const onGenerate = vi.fn();
    const onGeneratePrompts = vi.fn();
    render(
      <SceneArtModal
        {...baseProps}
        onGenerate={onGenerate}
        onGeneratePrompts={onGeneratePrompts}
        error="ComfyUI timed out."
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("ComfyUI timed out.");
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onGenerate).toHaveBeenCalledTimes(1);
    expect(onGeneratePrompts).not.toHaveBeenCalled();
  });

  it("retries whichever generate action was attempted last (prompts)", () => {
    const onGenerate = vi.fn();
    const onGeneratePrompts = vi.fn();
    const { rerender } = render(
      <SceneArtModal
        {...baseProps}
        onGenerate={onGenerate}
        onGeneratePrompts={onGeneratePrompts}
        error={null}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /generate prompts/i }));
    expect(onGeneratePrompts).toHaveBeenCalledTimes(1);

    rerender(
      <SceneArtModal
        {...baseProps}
        onGenerate={onGenerate}
        onGeneratePrompts={onGeneratePrompts}
        error="Could not reach the prompt writer."
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onGeneratePrompts).toHaveBeenCalledTimes(2);
    expect(onGenerate).not.toHaveBeenCalled();
  });

  it("names the operation instead of a generic failure message", () => {
    render(<SceneArtModal {...baseProps} error="Something went wrong." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not render the scene art.");
  });
});
