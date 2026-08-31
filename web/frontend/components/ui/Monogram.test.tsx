import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Monogram } from "./Monogram";

describe("Monogram", () => {
  it("keeps the character colour on the ring, where 3:1 is the bar", () => {
    render(<Monogram mono="MV" color="#8E2B1C" />);
    const el = screen.getByText("MV");
    expect(el).toBeInTheDocument();
    // jsdom normalises hex to rgb().
    expect(el.style.border).toContain("rgb(142, 43, 28)");
  });

  it("darkens the INITIALS toward the parchment ground's own ink", () => {
    // Bold 10-13px of a character colour on the fixed #EDE3CD circle measured
    // 3.11:1 and 3.86:1. The mix is toward a dark ink rather than the theme's,
    // because this ground is cream in every theme — mixing toward the theme ink
    // would make Ember and Slate worse, not better.
    render(<Monogram mono="MV" color="#8E2B1C" />);
    const el = screen.getByText("MV");
    expect(el.style.color).toBe(
      "color-mix(in oklab, rgb(142, 43, 28) 60%, rgb(36, 27, 16))",
    );
  });

  it("leaves the colour alone on a non-default ground, where the recipe would not hold", () => {
    render(<Monogram mono="MV" color="#8E2B1C" bg="#101010" />);
    expect(screen.getByText("MV").style.color).toBe("rgb(142, 43, 28)");
  });

  it("renders the portrait image (with the colored ring) when src is given", () => {
    render(<Monogram mono="MV" color="#8E2B1C" src="/media/portraits/x.webp" alt="Portrait of Mei" />);
    const img = screen.getByAltText("Portrait of Mei");
    expect(img).toHaveAttribute("src", "/media/portraits/x.webp");
    expect(screen.queryByText("MV")).not.toBeInTheDocument();
  });
});
