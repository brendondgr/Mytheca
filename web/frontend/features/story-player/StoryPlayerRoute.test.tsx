import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StoryPlayerRoute } from "./StoryPlayerRoute";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

describe("StoryPlayerRoute", () => {
  it("shows a loading state, then renders the resolved scene", async () => {
    render(<StoryPlayerRoute storylineId="embergate" scenarioId="embergate" />);
    // Initial loading curtain.
    expect(
      screen.getByRole("status", { name: /loading the scene/i }),
    ).toBeInTheDocument();
    // Resolves to the real scene (header title from the backend scenario).
    await waitFor(() =>
      expect(
        screen.getAllByText(/The Embergate Conspiracy/i).length,
      ).toBeGreaterThan(0),
    );
  });

  it("shows an error + retry when the scene cannot be resolved", async () => {
    render(<StoryPlayerRoute storylineId="embergate" scenarioId="missing" />);
    await waitFor(() =>
      expect(screen.getByText(/could not be raised/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /library/i })).toBeInTheDocument();
  });
});
