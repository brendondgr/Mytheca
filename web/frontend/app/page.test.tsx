import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import Home from "./page";

// The library mounts and fetches from `@/lib/api`; back it with the seed.
vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

describe("Home (library) route", () => {
  it("renders the VELORA wordmark and the library sections", () => {
    render(<Home />);
    expect(screen.getByText("VELORA")).toBeInTheDocument();
    expect(
      screen.getByRole("tablist", { name: /library sections/i }),
    ).toBeInTheDocument();
  });
});
