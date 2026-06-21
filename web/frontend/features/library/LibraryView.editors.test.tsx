import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { LibraryView } from "./LibraryView";

describe("LibraryView — editors & modals", () => {
  it("creates a character via the Create menu", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    await user.click(screen.getByRole("button", { name: /\+ create/i }));
    await user.click(screen.getByRole("button", { name: /forge a character/i }));

    const dialog = screen.getByRole("dialog");
    const nameInput = within(dialog).getByLabelText(/display name/i);
    await user.type(nameInput, "Test Hero");
    expect(nameInput).toHaveValue("Test Hero");
    const submitBtn = within(dialog).getByRole("button", { name: /add to cast/i });
    expect(submitBtn).toBeEnabled();
    await user.click(submitBtn);

    expect(screen.getByText("Test Hero")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens a character profile from a scenario card's cast", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    const viewButtons = screen.getAllByRole("button", {
      name: /view maerin voss/i,
    });
    await user.click(viewButtons[0]);

    const dialog = screen.getByRole("dialog", { name: /maerin voss/i });
    expect(
      within(dialog).getByText("She answers to the Drowned Court."),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: /edit character/i }),
    ).toBeInTheDocument();
  });

  it("previews the begin-scene with a link into the player", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    await user.click(screen.getByRole("button", { name: /begin scene/i }));

    const dialog = screen.getByRole("dialog", {
      name: /the embergate conspiracy/i,
    });
    expect(
      within(dialog).getByRole("link", { name: /enter scene/i }),
    ).toHaveAttribute("href", "/play/embergate");
  });

  it("edits a character via the card pencil", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    await user.click(screen.getByRole("tab", { name: /characters/i }));
    await user.click(screen.getByRole("button", { name: /edit maerin voss/i }));

    const dialog = screen.getByRole("dialog");
    const nameInput = within(dialog).getByLabelText(/display name/i);
    expect(nameInput).toHaveValue("Maerin Voss");
    await user.clear(nameInput);
    await user.type(nameInput, "Maerin Reborn");
    await user.click(within(dialog).getByRole("button", { name: /save changes/i }));

    expect(screen.getByText("Maerin Reborn")).toBeInTheDocument();
  });
});
