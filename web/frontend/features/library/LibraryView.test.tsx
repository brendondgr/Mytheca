import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { LibraryView } from "./LibraryView";

describe("LibraryView", () => {
  it("opens on the Scenarios tab with the seeded scenarios", () => {
    render(<LibraryView />);
    expect(screen.getByRole("tab", { name: /scenarios/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // appears in both the carousel slide and the scenario card
    expect(
      screen.getAllByText("The Embergate Conspiracy").length,
    ).toBeGreaterThan(0);
  });

  it("switches to Characters and renders the seeded cast", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    await user.click(screen.getByRole("tab", { name: /characters/i }));
    expect(screen.getByText("Maerin Voss")).toBeInTheDocument();
    expect(screen.getByText("Captain Doran Hale")).toBeInTheDocument();
  });

  it("filters the visible cards by search", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    await user.click(screen.getByRole("tab", { name: /characters/i }));
    await user.type(
      screen.getByRole("searchbox", { name: /search the library/i }),
      "oracle",
    );
    expect(screen.getByText("Nyssa, Oracle of Salt")).toBeInTheDocument();
    expect(screen.queryByText("Maerin Voss")).not.toBeInTheDocument();
  });

  it("expands a character to reveal hidden details", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    await user.click(screen.getByRole("tab", { name: /characters/i }));
    const summary = screen.getByRole("button", { name: /^maerin voss/i });
    expect(summary).toHaveAttribute("aria-expanded", "false");
    await user.click(summary);
    expect(summary).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByText("She answers to the Drowned Court."),
    ).toBeInTheDocument();
  });
});
