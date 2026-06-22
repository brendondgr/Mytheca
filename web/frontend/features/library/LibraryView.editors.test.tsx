import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { LibraryView } from "./LibraryView";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

describe("LibraryView — editors & modals", () => {
  it("creates a character via the Create menu", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    // Wait for the initial load so the active storyline is set before creating.
    await screen.findAllByText("The Embergate Conspiracy");

    await user.click(screen.getByRole("button", { name: /\+ create/i }));
    await user.click(screen.getByRole("button", { name: /forge a character/i }));

    const dialog = screen.getByRole("dialog");
    const nameInput = within(dialog).getByLabelText(/display name/i);
    await user.type(nameInput, "Test Hero");
    expect(nameInput).toHaveValue("Test Hero");
    const submitBtn = within(dialog).getByRole("button", { name: /add to cast/i });
    expect(submitBtn).toBeEnabled();
    await user.click(submitBtn);

    expect(await screen.findByText("Test Hero")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("creates a storyline via the switcher's write-first modal", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    await screen.findAllByText("The Embergate Conspiracy");

    // Open the storyline switcher, then the create action.
    await user.click(screen.getByTitle(/switch storyline/i));
    await user.click(screen.getByRole("button", { name: /new storyline/i }));

    const dialog = screen.getByRole("dialog");
    // Future seams are visible but non-functional.
    expect(within(dialog).getByText(/drag context files here/i)).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: /draft with velora/i }),
    ).toBeDisabled();
    expect(
      within(dialog).getByLabelText(/describe the world to draft/i),
    ).toBeDisabled();

    // Title is required: the create button is disabled until it's filled.
    const createBtn = within(dialog).getByRole("button", { name: /create world/i });
    expect(createBtn).toBeDisabled();

    await user.type(within(dialog).getByLabelText(/title/i), "Tidefall");
    await user.type(
      within(dialog).getByLabelText(/premise/i),
      "A sunken archipelago.\n\nThree fleets vie for the last dry harbor.",
    );
    expect(createBtn).toBeEnabled();
    await user.click(createBtn);

    // The new world becomes active (its title shows in the switcher) and the modal closes.
    expect(await screen.findByText("Tidefall")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens a character profile from a scenario card's cast", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    const viewButtons = await screen.findAllByRole("button", {
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
    await user.click(await screen.findByRole("button", { name: /begin scene/i }));

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
    await user.click(await screen.findByRole("button", { name: /edit maerin voss/i }));

    const dialog = screen.getByRole("dialog");
    const nameInput = within(dialog).getByLabelText(/display name/i);
    expect(nameInput).toHaveValue("Maerin Voss");
    await user.clear(nameInput);
    await user.type(nameInput, "Maerin Reborn");
    await user.click(within(dialog).getByRole("button", { name: /save changes/i }));

    expect(await screen.findByText("Maerin Reborn")).toBeInTheDocument();
  });
});
