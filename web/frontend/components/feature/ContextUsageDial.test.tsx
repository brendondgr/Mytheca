import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ContextUsageDial } from "./ContextUsageDial";

/** The coloured value arc is the last <circle> (the first is the track). */
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

  it("is a button labelled with the exact usage (counts, percent, provenance)", () => {
    render(<ContextUsageDial usedTokens={5200} maxTokens={16384} exact />);
    const dial = screen.getByRole("button", { name: /context usage/i });
    const label = dial.getAttribute("aria-label") ?? "";
    expect(label).toContain("5.2K of 16.4K tokens");
    expect(label).toContain("exact");
    // 5200 / 16384 ≈ 32%.
    expect(label).toContain("32%");
  });

  it("marks the figure as estimated when not exact", () => {
    render(<ContextUsageDial usedTokens={5200} maxTokens={16384} />);
    const dial = screen.getByRole("button", { name: /context usage/i });
    expect(dial.getAttribute("aria-label")).toContain("estimated");
  });

  it("exposes the usage only via a tooltip — no number in the ring centre", () => {
    render(<ContextUsageDial usedTokens={5200} maxTokens={16384} exact />);
    // The count lives in the tooltip element, not printed inside the dial button.
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip.textContent).toContain("5.2K of 16.4K tokens");
    const dial = screen.getByRole("button", { name: /context usage/i });
    // The button renders only the SVG ring (no visible text node).
    expect(dial.textContent).toBe("");
  });

  it("is green (text-success) below 50%", () => {
    render(<ContextUsageDial usedTokens={4000} maxTokens={16384} />); // ≈ 24%
    const dial = screen.getByRole("button", { name: /context usage/i });
    expect(dial.className).toContain("text-success");
    expect(dial.className).not.toContain("text-gold");
    expect(dial.className).not.toContain("text-danger");
  });

  it("is gold (text-gold) between 50% and 75%", () => {
    render(<ContextUsageDial usedTokens={9000} maxTokens={16384} />); // ≈ 55%
    expect(screen.getByRole("button", { name: /context usage/i }).className).toContain("text-gold");
  });

  it("is danger (text-danger) at or above 75%", () => {
    render(<ContextUsageDial usedTokens={14000} maxTokens={16384} />); // ≈ 85%
    expect(screen.getByRole("button", { name: /context usage/i }).className).toContain("text-danger");
  });

  it("is danger at exactly the 75% threshold", () => {
    render(<ContextUsageDial usedTokens={12000} maxTokens={16000} />); // 75%
    expect(screen.getByRole("button", { name: /context usage/i }).className).toContain("text-danger");
  });

  it("is gold at exactly the 50% threshold", () => {
    render(<ContextUsageDial usedTokens={8000} maxTokens={16000} />); // 50%
    expect(screen.getByRole("button", { name: /context usage/i }).className).toContain("text-gold");
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
