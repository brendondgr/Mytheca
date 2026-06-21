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
});
