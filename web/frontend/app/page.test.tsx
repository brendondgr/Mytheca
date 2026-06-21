import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Home from "./page";

describe("Home placeholder", () => {
  it("renders the Velora wordmark", () => {
    render(<Home />);
    expect(
      screen.getByRole("heading", { name: /velora/i }),
    ).toBeInTheDocument();
  });
});
