import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import StorylinePage from "./page";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

describe("/{storylineId} route", () => {
  it("renders the Library scoped to the storyline id", async () => {
    const ui = await StorylinePage({
      params: Promise.resolve({ storylineId: "embergate" }),
    });
    render(ui);
    expect(screen.getByText("MYTHECA")).toBeInTheDocument();
    expect(
      screen.getByRole("tablist", { name: /library sections/i }),
    ).toBeInTheDocument();
  });
});
