import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { GhostwriteButton } from "./GhostwriteButton";

const setup = (over: Partial<React.ComponentProps<typeof GhostwriteButton>> = {}) => {
  const props = { onGhostwrite: vi.fn(), onUndo: vi.fn(), ...over };
  render(<GhostwriteButton {...props} />);
  return props;
};

describe("GhostwriteButton", () => {
  it("is disabled with an empty message box — the box is the input", () => {
    setup({ canGhostwrite: false });
    expect(screen.getByRole("button", { name: /write this line for me/i })).toBeDisabled();
  });

  it("drafts from the note in the box", async () => {
    const user = userEvent.setup();
    const props = setup({ canGhostwrite: true });
    await user.click(screen.getByRole("button", { name: /write this line for me/i }));
    expect(props.onGhostwrite).toHaveBeenCalled();
  });

  it("announces that it is drafting", () => {
    setup({ canGhostwrite: true, running: true });
    const status = screen.getByText(/drafting your line/i);
    expect(status).toHaveAttribute("aria-live", "polite");
  });

  it("cannot be pressed twice while drafting", () => {
    setup({ canGhostwrite: true, running: true });
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("offers Undo once a draft has replaced the note", async () => {
    const user = userEvent.setup();
    const props = setup({ canUndo: true });
    await user.click(screen.getByRole("button", { name: /undo the drafted line/i }));
    expect(props.onUndo).toHaveBeenCalled();
  });

  it("does not offer Undo while still drafting", () => {
    setup({ canUndo: true, running: true, canGhostwrite: true });
    expect(screen.queryByRole("button", { name: /undo/i })).not.toBeInTheDocument();
  });
});
