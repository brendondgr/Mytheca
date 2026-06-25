import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { LibraryView } from "./LibraryView";
import * as api from "@/lib/api";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

async function openCharacterCreator(user: ReturnType<typeof userEvent.setup>) {
  render(<LibraryView />);
  await screen.findAllByText("The Embergate Conspiracy");
  await user.click(screen.getByRole("button", { name: /\+ create/i }));
  await user.click(screen.getByRole("button", { name: /forge a character/i }));
  return screen.getByRole("dialog");
}

describe("CharacterModal — agentic creator", () => {
  it("drafts a full character from a seed into the form", async () => {
    const user = userEvent.setup();
    const dialog = await openCharacterCreator(user);

    await user.type(
      within(dialog).getByLabelText(/describe the character to draft/i),
      "A by-the-book harbor captain.",
    );
    const draftBtn = within(dialog).getByRole("button", { name: /draft with velora/i });
    expect(draftBtn).toBeEnabled();
    await user.click(draftBtn);

    expect(vi.mocked(api.draftCharacter)).toHaveBeenCalled();
    await waitFor(() =>
      expect(within(dialog).getByLabelText(/display name/i)).toHaveValue("Drafted Hero"),
    );
    expect(within(dialog).getByLabelText(/^appearance$/i)).toHaveValue("A drafted appearance.");
    expect(within(dialog).getByLabelText(/^background$/i)).toHaveValue("A drafted background.");
    expect(within(dialog).getByLabelText(/^personality$/i)).toHaveValue("A drafted personality.");
  });

  it("generates portrait prompts, then renders a portrait preview", async () => {
    const user = userEvent.setup();
    const dialog = await openCharacterCreator(user);

    // A description enables "Generate prompts".
    await user.type(within(dialog).getByLabelText(/^appearance$/i), "A young orc warrior.");
    await user.click(within(dialog).getByRole("button", { name: /generate prompts/i }));
    await waitFor(() => {
      const positive = within(dialog).getByLabelText(
        /portrait positive prompt/i,
      ) as HTMLTextAreaElement;
      expect(positive.value).toContain("watercolor portrait");
    });

    // Rendering the portrait calls ComfyUI and shows the WebP preview.
    await user.click(within(dialog).getByRole("button", { name: /generate portrait/i }));
    expect(vi.mocked(api.generatePortrait)).toHaveBeenCalledWith(
      expect.objectContaining({ positive: expect.stringContaining("watercolor portrait") }),
    );
    await waitFor(() =>
      expect(within(dialog).getAllByAltText(/portrait of/i).length).toBeGreaterThan(0),
    );
  });

  it("proposes starting stats keyed to the world's schema", async () => {
    const user = userEvent.setup();
    const dialog = await openCharacterCreator(user);

    await user.click(within(dialog).getByRole("button", { name: /❖ propose/i }));
    await waitFor(() =>
      expect(within(dialog).getByLabelText(/health starting value/i)).toHaveValue(90),
    );
    expect(within(dialog).getByLabelText(/trust starting value/i)).toHaveValue(1);
  });

  it("grounds the draft with a dropped reference file's text", async () => {
    const user = userEvent.setup();
    const dialog = await openCharacterCreator(user);

    const file = new File(["Born of the salt marsh. DOSSIER_MARKER"], "dossier.md", {
      type: "text/markdown",
    });
    await user.upload(within(dialog).getByLabelText(/browse files/i), file);
    expect(
      await within(dialog).findByRole("button", { name: /remove dossier\.md/i }),
    ).toBeInTheDocument();

    await user.type(
      within(dialog).getByLabelText(/describe the character to draft/i),
      "A marsh-born scout.",
    );
    await user.click(within(dialog).getByRole("button", { name: /draft with velora/i }));
    await waitFor(() =>
      expect(vi.mocked(api.draftCharacter)).toHaveBeenCalledWith(
        "A marsh-born scout.",
        expect.stringContaining("DOSSIER_MARKER"),
        expect.any(String),
      ),
    );
  });
});
