import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Monogram } from "./Monogram";

describe("Monogram", () => {
  it("renders the initials styled with the character color", () => {
    render(<Monogram mono="MV" color="#8E2B1C" />);
    const el = screen.getByText("MV");
    expect(el).toBeInTheDocument();
    expect(el).toHaveStyle({ color: "#8E2B1C" });
  });

  it("renders the portrait image (with the colored ring) when src is given", () => {
    render(<Monogram mono="MV" color="#8E2B1C" src="/media/portraits/x.webp" alt="Portrait of Mei" />);
    const img = screen.getByAltText("Portrait of Mei");
    expect(img).toHaveAttribute("src", "/media/portraits/x.webp");
    expect(screen.queryByText("MV")).not.toBeInTheDocument();
  });
});
