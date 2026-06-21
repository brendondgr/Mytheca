import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Home from "./page";

describe("Home (library) route", () => {
  it("renders the VELORA wordmark and the library sections", () => {
    render(<Home />);
    expect(screen.getByText("VELORA")).toBeInTheDocument();
    expect(
      screen.getByRole("tablist", { name: /library sections/i }),
    ).toBeInTheDocument();
  });
});
