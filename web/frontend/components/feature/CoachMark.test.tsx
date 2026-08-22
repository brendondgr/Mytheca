import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CoachMark } from "./CoachMark";

describe("CoachMark", () => {
  it("is an aside, not a modal", () => {
    // The review ruled out a tour: no overlay, no backdrop, no focus trap. Announcing it as a
    // dialog would imply a modality it deliberately does not have.
    render(<CoachMark text="Type what you say." onDismiss={() => {}} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("says its one thing", () => {
    render(<CoachMark text="Type what you say." onDismiss={() => {}} />);
    expect(screen.getByText("Type what you say.")).toBeInTheDocument();
  });

  it("dismisses by button", () => {
    const onDismiss = vi.fn();
    render(<CoachMark text="x" onDismiss={onDismiss} />);
    fireEvent.click(screen.getByRole("button", { name: "Got it" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("dismisses by Escape", () => {
    // Anything dismissible only one way eventually traps someone.
    const onDismiss = vi.fn();
    render(<CoachMark text="x" onDismiss={onDismiss} />);
    fireEvent.keyDown(screen.getByRole("status"), { key: "Escape" });
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("gives the dismiss control a real hit area", () => {
    render(<CoachMark text="x" onDismiss={() => {}} />);
    // 24x24 minimum target (WCAG 2.5.8) — the glyph is small, the target is not.
    expect(screen.getByRole("button", { name: "Got it" }).className).toMatch(
      /h-\[24px\].*w-\[24px\]/,
    );
  });
});
