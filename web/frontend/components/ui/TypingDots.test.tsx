import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TypingDots } from "./TypingDots";

describe("TypingDots", () => {
  it("renders three dots, hidden from assistive tech (the label says it instead)", () => {
    render(<TypingDots />);
    const dots = screen.getByTestId("typing-dots");
    expect(dots).toHaveAttribute("aria-hidden", "true");
    expect(dots.querySelectorAll("span")).toHaveLength(3);
  });

  it("staggers the dots and gives each a visible static opacity", () => {
    // The app-wide reduced-motion rule strips `animation`; the base opacity is what keeps
    // the dots visible once it does, so it must never be 0.
    render(<TypingDots />);
    const dots = Array.from(screen.getByTestId("typing-dots").querySelectorAll("span"));
    const delays = dots.map((d) => (d as HTMLElement).style.animation);
    expect(delays[0]).toContain("0s");
    expect(delays[1]).toContain("0.2s");
    expect(delays[2]).toContain("0.4s");
    for (const d of dots) expect(Number((d as HTMLElement).style.opacity)).toBeGreaterThan(0);
  });

  it("honors a custom dot size", () => {
    render(<TypingDots size={6} />);
    const first = screen.getByTestId("typing-dots").querySelector("span") as HTMLElement;
    expect(first.style.width).toBe("6px");
    expect(first.style.height).toBe("6px");
  });
});
