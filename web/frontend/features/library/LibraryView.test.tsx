import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { LibraryView } from "./LibraryView";

// The Library now loads from the backend; back `@/lib/api` with the seed.
vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

describe("LibraryView", () => {
  it("opens on the Scenarios tab with the seeded scenarios", async () => {
    render(<LibraryView />);
    expect(screen.getByRole("tab", { name: /scenarios/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // appears in both the carousel slide and the scenario card (loaded async)
    expect(
      (await screen.findAllByText("The Embergate Conspiracy")).length,
    ).toBeGreaterThan(0);
  });

  it("switches to Characters and renders the seeded cast", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    await user.click(screen.getByRole("tab", { name: /characters/i }));
    // findAllByText: names appear in both the carousel cast column and character cards
    expect((await screen.findAllByText("Maerin Voss")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Captain Doran Hale").length).toBeGreaterThan(0);
  });

  it("filters the visible cards by search", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    await user.click(screen.getByRole("tab", { name: /characters/i }));
    await user.type(
      screen.getByRole("searchbox", { name: /search the library/i }),
      "oracle",
    );
    // Nyssa may appear in both the character card and an inactive carousel slide;
    // scope to the Characters panel so the assertion is about the filtered list.
    const charPanel = screen.getByRole("tabpanel", { name: /characters/i });
    expect(await within(charPanel).findByText("Nyssa, Oracle of Salt")).toBeInTheDocument();
    // Maerin Voss should be filtered from the character list (carousel still shows her).
    expect(within(charPanel).queryByText("Maerin Voss")).not.toBeInTheDocument();
  });

  it("opens a character profile modal when a character card is clicked", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    await user.click(screen.getByRole("tab", { name: /characters/i }));
    const charPanel = screen.getByRole("tabpanel", { name: /characters/i });
    const card = await within(charPanel).findByRole("button", { name: /view maerin voss/i });
    // Card is a plain button — no disclosure attributes.
    expect(card).not.toHaveAttribute("aria-expanded");
    await user.click(card);
    // Profile modal opens.
    const dialog = screen.getByRole("dialog", { name: /maerin voss/i });
    expect(
      within(dialog).getByText("She answers to the Drowned Court."),
    ).toBeInTheDocument();
  });
});
