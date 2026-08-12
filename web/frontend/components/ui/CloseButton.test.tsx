import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { CloseButton } from "./CloseButton";

describe("CloseButton", () => {
  it("is reachable by its accessible name and closes on click", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<CloseButton onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("routes its hover scale through the pointer-gated class", () => {
    render(<CloseButton onClose={() => {}} />);
    const button = screen.getByRole("button", { name: "Close" });
    // The scale must NOT be a bare `hover:scale-110` utility: Tailwind's hover
    // variant is not gated, so on touch the state is applied on tap and sticks
    // until the user taps elsewhere — leaving a permanently enlarged glyph.
    // `.close-button-hover` carries it behind @media (hover: hover).
    expect(button).toHaveClass("close-button-hover");
    expect(button.className).not.toMatch(/hover:scale/);
  });

  it("can be disabled", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<CloseButton onClose={onClose} disabled />);
    const button = screen.getByRole("button", { name: "Close" });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(onClose).not.toHaveBeenCalled();
  });
});
