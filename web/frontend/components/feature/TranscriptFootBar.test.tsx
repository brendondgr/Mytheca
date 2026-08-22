import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { TranscriptFootBar } from "./TranscriptFootBar";

const setup = (over: Partial<React.ComponentProps<typeof TranscriptFootBar>> = {}) => {
  const props = { onContinue: vi.fn(), onCreateImage: vi.fn(), ...over };
  render(<TranscriptFootBar {...props} />);
  return props;
};

describe("TranscriptFootBar", () => {
  it("runs a turn with no player line", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.click(screen.getByRole("button", { name: /continue/i }));
    expect(props.onContinue).toHaveBeenCalled();
  });

  it("says what Continue is for, rather than leaving the player to guess", () => {
    setup();
    expect(screen.getByText(/let the scene carry on without you/i)).toBeInTheDocument();
  });

  it("puts Continue before Create image in the tab order", async () => {
    const user = userEvent.setup();
    setup();
    await user.tab();
    // Continue advances the story; Create image pictures the story it is already in.
    expect(screen.getByRole("button", { name: /continue/i })).toHaveFocus();
  });

  it("shows progress and blocks a second press while continuing", () => {
    setup({ continuing: true });
    expect(screen.getByRole("button", { name: /continuing/i })).toBeDisabled();
  });

  it("disables Continue while a turn is streaming", () => {
    setup({ disabled: true });
    expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();
  });

  it("still offers Create image", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.click(screen.getByRole("button", { name: /^go$/i }));
    expect(props.onCreateImage).toHaveBeenCalled();
  });
});
