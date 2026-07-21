import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { AppHeader } from "./AppHeader";

describe("AppHeader Mytheca brand", () => {
  it("renders the MYTHECA wordmark", () => {
    render(<AppHeader query="" onQuery={vi.fn()} />);
    expect(screen.getByText("MYTHECA")).toBeInTheDocument();
  });

  it("renders the theme-aware brand emblem (CSS swaps the icon per theme)", () => {
    const { container } = render(<AppHeader query="" onQuery={vi.fn()} />);
    // The emblem is a decorative span; `.mytheca-brandmark` carries the dark icon
    // by default and CSS (.theme-dark/.theme-slate .mytheca-brandmark) swaps to
    // the cream icon on the dark themes.
    const emblem = container.querySelector(".mytheca-brandmark");
    expect(emblem).not.toBeNull();
    expect(emblem).toHaveAttribute("aria-hidden");
  });
});
