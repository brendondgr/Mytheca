import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { BeatTakePager } from "./BeatTakePager";

describe("BeatTakePager", () => {
  it("shows nothing when the beat has only one version", () => {
    const { container } = render(<BeatTakePager count={1} active={0} onSelect={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("reads as a position in a set", () => {
    render(<BeatTakePager count={3} active={1} onSelect={vi.fn()} />);
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
  });

  it("announces the count politely, because flipping swaps the prose above it", () => {
    render(<BeatTakePager count={2} active={0} onSelect={vi.fn()} />);
    expect(screen.getByText("1 / 2")).toHaveAttribute("aria-live", "polite");
  });

  it("goes back to an earlier take", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<BeatTakePager count={2} active={1} onSelect={onSelect} label="Mei's beat" />);
    await user.click(screen.getByRole("button", { name: /previous version of mei's beat/i }));
    expect(onSelect).toHaveBeenCalledWith(0);
  });

  it("goes forward", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<BeatTakePager count={3} active={0} onSelect={onSelect} />);
    await user.click(screen.getByRole("button", { name: /next version/i }));
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("cannot step past either end", () => {
    const { rerender } = render(<BeatTakePager count={2} active={0} onSelect={vi.fn()} />);
    expect(screen.getByRole("button", { name: /previous version/i })).toBeDisabled();
    rerender(<BeatTakePager count={2} active={1} onSelect={vi.fn()} />);
    expect(screen.getByRole("button", { name: /next version/i })).toBeDisabled();
  });

  it("is disabled while a turn is streaming", () => {
    render(<BeatTakePager count={2} active={0} onSelect={vi.fn()} disabled />);
    for (const b of screen.getAllByRole("button")) expect(b).toBeDisabled();
  });
});
