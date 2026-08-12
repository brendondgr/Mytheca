import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { act } from "react";
import { StorylineDeleteModal } from "./StorylineDeleteModal";
import { INDICATOR_DELAY_MS } from "@/hooks/use-delayed-flag";
import type { Storyline } from "@/lib/types";

afterEach(() => vi.useRealTimers());

const storyline: Storyline = {
  id: "sl-1",
  title: "The Embergate Conspiracy",
  scenarios: [],
  characters: [],
  settings: [],
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any as Storyline;

describe("StorylineDeleteModal", () => {
  it("disables the actions immediately, but shows no spinner for a fast delete", () => {
    vi.useFakeTimers();
    render(
      <StorylineDeleteModal
        storyline={storyline}
        pending
        error={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    const confirm = screen.getByRole("button", { name: "Delete World" });
    expect(confirm).toBeDisabled();
    // The row is marked busy immediately, well before the spinner is shown.
    expect(confirm.parentElement).toHaveAttribute("aria-busy", "true");

    act(() => void vi.advanceTimersByTime(INDICATOR_DELAY_MS - 1));
    expect(confirm).not.toHaveAttribute("aria-busy", "true");
  });

  it("shows a spinner without reflowing once the delete outlasts the delay gate", () => {
    vi.useFakeTimers();
    render(
      <StorylineDeleteModal
        storyline={storyline}
        pending
        error={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    act(() => void vi.advanceTimersByTime(INDICATOR_DELAY_MS));
    const confirm = screen.getByRole("button", { name: "Deleting storyline" });
    expect(confirm).toHaveAttribute("aria-busy", "true");
  });

  it("renders no busy state once the delete has resolved", () => {
    render(
      <StorylineDeleteModal
        storyline={storyline}
        pending={false}
        error={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const confirm = screen.getByRole("button", { name: "Delete World" });
    expect(confirm).toBeEnabled();
    expect(confirm).not.toHaveAttribute("aria-busy");
  });
});
