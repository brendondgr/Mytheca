import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { LibraryView } from "./LibraryView";
import * as api from "@/lib/api";

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
    // The seed box is live; "Draft with Velora" stays disabled until a seed is typed.
    const seedBox = within(dialog).getByLabelText(/describe the world to draft/i);
    expect(seedBox).toBeEnabled();
    expect(
      within(dialog).getByRole("button", { name: /draft with velora/i }),
    ).toBeDisabled();

    // Title is required: the create button is disabled until it's filled.
    const createBtn = within(dialog).getByRole("button", { name: /create world/i });
    expect(createBtn).toBeDisabled();

    await user.type(within(dialog).getByLabelText(/title/i), "Tidefall");
    await user.type(
      within(dialog).getByLabelText(/premise/i),
      "A sunken archipelago.\n\nThree fleets vie for the last dry harbor.",
    );

    // Pick a custom seal: a star symbol and the teal color.
    await user.click(within(dialog).getByRole("button", { name: "Symbol ★" }));
    await user.click(within(dialog).getByRole("button", { name: "Color #2F7D6B" }));

    expect(createBtn).toBeEnabled();
    await user.click(createBtn);

    // The chosen seal is sent to the backend on create.
    expect(vi.mocked(api.createStoryline)).toHaveBeenCalledWith(
      expect.objectContaining({ symbol: "★", symbolColor: "#2F7D6B" }),
    );

    // The new world becomes active (its title shows in the switcher) and the modal closes.
    expect(await screen.findByText("Tidefall")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("drafts metadata from a seed and persists a generated World Primer", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    await screen.findAllByText("The Embergate Conspiracy");

    await user.click(screen.getByTitle(/switch storyline/i));
    await user.click(screen.getByRole("button", { name: /new storyline/i }));
    const dialog = screen.getByRole("dialog");

    // Seed → "Draft with Velora" fills the metadata fields from the agent.
    await user.type(
      within(dialog).getByLabelText(/describe the world to draft/i),
      "A drowned harbor town.",
    );
    const draftBtn = within(dialog).getByRole("button", { name: /draft with velora/i });
    expect(draftBtn).toBeEnabled();
    await user.click(draftBtn);

    expect(vi.mocked(api.draftStoryline)).toHaveBeenCalledWith(
      "A drowned harbor town.",
      undefined,
    );
    const titleInput = within(dialog).getByLabelText(/title/i);
    await waitFor(() => expect(titleInput).toHaveValue("Drafted World"));
    expect(within(dialog).getByLabelText(/^premise$/i)).toHaveValue(
      "Drafted premise paragraph one.\n\nDrafted premise paragraph two.",
    );

    // Generate the World Primer from the seed + premise; it lands in the field.
    await user.click(within(dialog).getByRole("button", { name: /generate primer/i }));
    expect(vi.mocked(api.generateWorldPrimer)).toHaveBeenCalled();
    const primerBox = within(dialog).getByLabelText(/^world primer$/i);
    await waitFor(() =>
      expect(primerBox).toHaveValue(
        "A generated, agent-facing primer.\n\nThree powers govern the world.",
      ),
    );

    // Create — the generated primer is persisted alongside the metadata.
    await user.click(within(dialog).getByRole("button", { name: /create world/i }));
    expect(vi.mocked(api.createStoryline)).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Drafted World",
        worldPrimer:
          "A generated, agent-facing primer.\n\nThree powers govern the world.",
      }),
    );
  });

  it("edits a storyline via the switcher", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    await screen.findAllByText("The Embergate Conspiracy");

    await user.click(screen.getByTitle(/switch storyline/i));
    await user.click(screen.getByRole("button", { name: /^edit embergate$/i }));

    const dialog = screen.getByRole("dialog");
    const titleInput = within(dialog).getByLabelText(/title/i);
    expect(titleInput).toHaveValue("Embergate"); // prefilled from the storyline
    await user.clear(titleInput);
    await user.type(titleInput, "Embergate Reborn");
    await user.click(within(dialog).getByRole("button", { name: /save changes/i }));

    // The switcher reflects the new name and the modal closes.
    expect(await screen.findByText("Embergate Reborn")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("deletes a storyline after a confirmation step", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    await screen.findAllByText("The Embergate Conspiracy");

    await user.click(screen.getByTitle(/switch storyline/i));
    await user.click(screen.getByRole("button", { name: /^delete embergate$/i }));

    // A confirmation modal appears before anything is deleted.
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/can.t be undone/i)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /delete world/i }));

    expect(vi.mocked(api.deleteStoryline)).toHaveBeenCalledWith("embergate");
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
