import { render, screen, within } from "@testing-library/react";
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

  it("navigates to the New Storyline page from the switcher", async () => {
    const { useRouter } = await import("next/navigation");
    const push = vi.mocked(useRouter().push);
    push.mockClear();
    const user = userEvent.setup();
    render(<LibraryView />);
    await screen.findAllByText("The Embergate Conspiracy");

    await user.click(screen.getByTitle(/switch storyline/i));
    await user.click(screen.getByRole("button", { name: /new storyline/i }));

    expect(push).toHaveBeenCalledWith("/storylines/new");
  });

  it("navigates to the storyline edit page from the switcher pencil", async () => {
    const { useRouter } = await import("next/navigation");
    const push = vi.mocked(useRouter().push);
    push.mockClear();
    const user = userEvent.setup();
    render(<LibraryView />);
    await screen.findAllByText("The Embergate Conspiracy");

    await user.click(screen.getByTitle(/switch storyline/i));
    await user.click(screen.getByRole("button", { name: /^edit embergate$/i }));

    expect(push).toHaveBeenCalledWith("/storylines/embergate/edit");
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
    ).toHaveAttribute("href", "/embergate/embergate");
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

    // findAllByText: the updated name appears in both the carousel cast column
    // and the character card — either confirms the save succeeded.
    expect((await screen.findAllByText("Maerin Reborn")).length).toBeGreaterThan(0);
  });
});
