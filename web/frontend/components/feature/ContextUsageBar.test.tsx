import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ContextUsageBar } from "./ContextUsageBar";

describe("ContextUsageBar", () => {
  it("renders nothing when maxTokens is 0", () => {
    const { container } = render(<ContextUsageBar usedTokens={100} maxTokens={0} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when maxTokens is negative", () => {
    const { container } = render(<ContextUsageBar usedTokens={0} maxTokens={-1} />);
    expect(container.firstChild).toBeNull();
  });

  it("has role=progressbar with correct aria attributes", () => {
    render(<ContextUsageBar usedTokens={5000} maxTokens={16384} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "5000");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "16384");
    expect(bar).toHaveAttribute("aria-label", "Context usage");
  });

  it("aria-valuetext shows K-formatted used and max", () => {
    render(<ContextUsageBar usedTokens={5200} maxTokens={16384} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuetext", "5.2K of 16.4K tokens");
  });

  it("title tooltip shows K / K format", () => {
    render(<ContextUsageBar usedTokens={5200} maxTokens={16384} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("title", "5.2K / 16.4K tokens");
  });

  it("fill is green (bg-success) when percentage is below 50%", () => {
    render(<ContextUsageBar usedTokens={4000} maxTokens={16384} />);
    // 4000 / 16384 ≈ 24.4% — green
    const fill = screen.getByRole("progressbar").firstChild as HTMLElement;
    expect(fill.className).toContain("bg-success");
    expect(fill.className).not.toContain("bg-gold");
    expect(fill.className).not.toContain("bg-danger");
  });

  it("fill is gold (bg-gold) when percentage is between 50% and 75%", () => {
    render(<ContextUsageBar usedTokens={9000} maxTokens={16384} />);
    // 9000 / 16384 ≈ 54.9% — gold
    const fill = screen.getByRole("progressbar").firstChild as HTMLElement;
    expect(fill.className).toContain("bg-gold");
    expect(fill.className).not.toContain("bg-success");
    expect(fill.className).not.toContain("bg-danger");
  });

  it("fill is danger (bg-danger) when percentage is 75% or above", () => {
    render(<ContextUsageBar usedTokens={14000} maxTokens={16384} />);
    // 14000 / 16384 ≈ 85.4% — danger
    const fill = screen.getByRole("progressbar").firstChild as HTMLElement;
    expect(fill.className).toContain("bg-danger");
    expect(fill.className).not.toContain("bg-success");
    expect(fill.className).not.toContain("bg-gold");
  });

  it("fill is danger at exactly 75% threshold", () => {
    // 75% of 16000 = 12000
    render(<ContextUsageBar usedTokens={12000} maxTokens={16000} />);
    const fill = screen.getByRole("progressbar").firstChild as HTMLElement;
    expect(fill.className).toContain("bg-danger");
  });

  it("fill is gold at exactly 50% threshold", () => {
    // 50% of 16000 = 8000
    render(<ContextUsageBar usedTokens={8000} maxTokens={16000} />);
    const fill = screen.getByRole("progressbar").firstChild as HTMLElement;
    expect(fill.className).toContain("bg-gold");
  });

  it("fill width caps at 100% when used > max", () => {
    render(<ContextUsageBar usedTokens={20000} maxTokens={16384} />);
    const fill = screen.getByRole("progressbar").firstChild as HTMLElement;
    expect(fill.style.width).toBe("100%");
  });

  it("fill width reflects percentage correctly", () => {
    // 8000 / 16000 = 50% exactly
    render(<ContextUsageBar usedTokens={8000} maxTokens={16000} />);
    const fill = screen.getByRole("progressbar").firstChild as HTMLElement;
    expect(fill.style.width).toBe("50%");
  });
});
