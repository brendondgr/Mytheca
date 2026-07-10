import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ContextUsageDial } from "./ContextUsageDial";

/** The coloured value arc is the second <circle> (the first is the track). */
function valueArc(): SVGCircleElement {
  const circles = document.querySelectorAll("circle");
  return circles[circles.length - 1] as unknown as SVGCircleElement;
}

describe("ContextUsageDial", () => {
  it("renders nothing when maxTokens is 0", () => {
    const { container } = render(<ContextUsageDial usedTokens={100} maxTokens={0} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when maxTokens is negative", () => {
    const { container } = render(<ContextUsageDial usedTokens={0} maxTokens={-1} />);
    expect(container.firstChild).toBeNull();
  });

  it("has role=progressbar with correct aria attributes", () => {
    render(<ContextUsageDial usedTokens={5000} maxTokens={16384} />);
    const dial = screen.getByRole("progressbar");
    expect(dial).toHaveAttribute("aria-valuenow", "5000");
    expect(dial).toHaveAttribute("aria-valuemin", "0");
    expect(dial).toHaveAttribute("aria-valuemax", "16384");
    expect(dial).toHaveAttribute("aria-label", "Context usage");
  });

  it("aria-valuetext + title show K-formatted counts and the exact qualifier", () => {
    render(<ContextUsageDial usedTokens={5200} maxTokens={16384} exact />);
    const dial = screen.getByRole("progressbar");
    expect(dial).toHaveAttribute("aria-valuetext", "5.2K of 16.4K tokens (exact)");
    expect(dial).toHaveAttribute("title", "5.2K / 16.4K tokens · exact");
  });

  it("marks the figure as estimated when not exact", () => {
    render(<ContextUsageDial usedTokens={5200} maxTokens={16384} />);
    const dial = screen.getByRole("progressbar");
    expect(dial).toHaveAttribute("aria-valuetext", "5.2K of 16.4K tokens (estimated)");
  });

  it("shows the used-token K count in the centre", () => {
    render(<ContextUsageDial usedTokens={5200} maxTokens={16384} />);
    expect(screen.getByText("5.2K")).toBeInTheDocument();
  });

  it("is green (text-success) below 50%", () => {
    render(<ContextUsageDial usedTokens={4000} maxTokens={16384} />); // ≈ 24%
    const dial = screen.getByRole("progressbar");
    expect(dial.className).toContain("text-success");
    expect(dial.className).not.toContain("text-gold");
    expect(dial.className).not.toContain("text-danger");
  });

  it("is gold (text-gold) between 50% and 75%", () => {
    render(<ContextUsageDial usedTokens={9000} maxTokens={16384} />); // ≈ 55%
    const dial = screen.getByRole("progressbar");
    expect(dial.className).toContain("text-gold");
  });

  it("is danger (text-danger) at or above 75%", () => {
    render(<ContextUsageDial usedTokens={14000} maxTokens={16384} />); // ≈ 85%
    const dial = screen.getByRole("progressbar");
    expect(dial.className).toContain("text-danger");
  });

  it("is danger at exactly the 75% threshold", () => {
    render(<ContextUsageDial usedTokens={12000} maxTokens={16000} />); // 75%
    expect(screen.getByRole("progressbar").className).toContain("text-danger");
  });

  it("is gold at exactly the 50% threshold", () => {
    render(<ContextUsageDial usedTokens={8000} maxTokens={16000} />); // 50%
    expect(screen.getByRole("progressbar").className).toContain("text-gold");
  });

  it("fills to a zero dash offset (100%) when used ≥ max", () => {
    render(<ContextUsageDial usedTokens={20000} maxTokens={16384} />);
    expect(Number(valueArc().getAttribute("stroke-dashoffset"))).toBeCloseTo(0, 5);
  });

  it("half-fills the arc at 50% (offset = half the circumference)", () => {
    render(<ContextUsageDial usedTokens={8000} maxTokens={16000} size={40} />);
    const arc = valueArc();
    const circumference = Number(arc.getAttribute("stroke-dasharray"));
    expect(Number(arc.getAttribute("stroke-dashoffset"))).toBeCloseTo(circumference / 2, 5);
  });
});
