import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach } from "vitest";
import { act } from "react";
import { LibraryView } from "./LibraryView";
import { CharacterModal } from "@/components/feature/CharacterModal";
import { INDICATOR_DELAY_MS } from "@/hooks/use-delayed-flag";
import type { useLibraryState } from "@/features/library/useLibraryState";
import * as api from "@/lib/api";

type Lib = ReturnType<typeof useLibraryState>;

function makeLib(overrides: Partial<Lib> = {}): Lib {
  return {
    modal: { type: "character", mode: "manual", editId: "c-1" },
    draft: { name: "Doran Hale", role: "Captain" },
    isValid: true,
    pending: false,
    generating: false,
    generatingPrompts: false,
    generatingPortrait: false,
    generatingVoice: false,
    generatingStats: false,
    applyingStats: false,
    error: null,
    activeField: null,
    draftStage: null,
    activeStorylineId: "sl-1",
    setDraft: vi.fn(),
    setMode: vi.fn(),
    closeModal: vi.fn(),
    submit: vi.fn(),
    deleteEntity: vi.fn(),
    draftCharacter: vi.fn(),
    generatePortraitPrompts: vi.fn(),
    generatePortrait: vi.fn(),
    proposeVoiceSamples: vi.fn(),
    proposeStartingStats: vi.fn(),
    applyStartingStats: vi.fn(),
    ...overrides,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any as Lib;
}

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
    const draftBtn = within(dialog).getByRole("button", { name: /draft with mytheca/i });
    expect(draftBtn).toBeEnabled();
    await user.click(draftBtn);

    expect(vi.mocked(api.draftCharacter)).toHaveBeenCalled();
    // Fields fill in one at a time (choreographed reveal) — wait for the last.
    await waitFor(() =>
      expect(within(dialog).getByLabelText(/display name/i)).toHaveValue("Drafted Hero"),
    );
    await waitFor(() => {
      expect(within(dialog).getByLabelText(/^appearance$/i)).toHaveValue("A drafted appearance.");
      expect(within(dialog).getByLabelText(/^background$/i)).toHaveValue("A drafted background.");
      expect(within(dialog).getByLabelText(/^personality$/i)).toHaveValue(
        "A drafted personality.",
      );
    });
    // Real-time bound: typing the seed plus the 150 ms-per-field choreographed reveal
    // runs ~4.4 s alone, which overruns the 5 s default under a loaded parallel suite.
  }, 15000);

  // Same choreography bound as the test above: this waits on the ~150ms-per-field
  // `use-field-reveal` sequence, which outruns Vitest's 5s default under full worker
  // concurrency. Its sibling already carried this budget; this one was missed.
  it("highlights the field being written and shows draft progress", { timeout: 15_000 }, async () => {
    const user = userEvent.setup();
    const dialog = await openCharacterCreator(user);

    await user.type(
      within(dialog).getByLabelText(/describe the character to draft/i),
      "A by-the-book harbor captain.",
    );
    await user.click(within(dialog).getByRole("button", { name: /draft with mytheca/i }));

    // The progress stepper appears during the draft…
    expect(
      await within(dialog).findByRole("group", { name: /character draft progress/i }),
    ).toBeInTheDocument();
    // …and at some point a field carries the live "editing now" highlight.
    await waitFor(() => {
      const active = dialog.querySelector(".mytheca-field-active");
      expect(active).not.toBeNull();
    });
  });

  it("generates portrait prompts, then renders a portrait preview", async () => {
    const user = userEvent.setup();
    const dialog = await openCharacterCreator(user);

    // A description enables "Generate prompts". The portrait flow lives in a
    // pop-up reached from the compact preview's "Edit image" button.
    await user.type(within(dialog).getByLabelText(/^appearance$/i), "A young orc warrior.");
    await user.click(within(dialog).getByRole("button", { name: /edit image/i }));
    const portrait = screen.getByRole("dialog", { name: /^portrait$/i });

    await user.click(within(portrait).getByRole("button", { name: /generate prompts/i }));
    await waitFor(() => {
      const positive = within(portrait).getByLabelText(
        /portrait positive prompt/i,
      ) as HTMLTextAreaElement;
      expect(positive.value).toContain("watercolor portrait");
    });

    // Rendering the portrait calls ComfyUI and shows the WebP preview.
    await user.click(within(portrait).getByRole("button", { name: /generate portrait/i }));
    expect(vi.mocked(api.generatePortrait)).toHaveBeenCalledWith(
      expect.objectContaining({ positive: expect.stringContaining("watercolor portrait") }),
    );
    await waitFor(() =>
      expect(screen.getAllByAltText(/portrait of/i).length).toBeGreaterThan(0),
    );
  });

  it("shows the Voice & tone section above Starting stats", async () => {
    const user = userEvent.setup();
    const dialog = await openCharacterCreator(user);
    const voice = within(dialog).getByText(/voice & tone/i);
    const stats = within(dialog).getByText(/starting stats/i);
    // Voice comes first — it's defined before stats.
    expect(voice.compareDocumentPosition(stats) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("proposes voice samples on demand into editable rows", async () => {
    const user = userEvent.setup();
    const dialog = await openCharacterCreator(user);

    // The Voice & tone "Propose" is the first ❖ Propose (it sits above stats).
    await user.click(within(dialog).getAllByRole("button", { name: /❖ propose/i })[0]);
    expect(vi.mocked(api.proposeVoiceSamples)).toHaveBeenCalled();
    await waitFor(() =>
      expect(within(dialog).getByLabelText(/sample 1 situation/i)).toHaveValue("greeted warmly"),
    );
    expect(within(dialog).getByLabelText(/sample 1 response/i)).toHaveValue("State your business.");
  });

  it("proposes starting stats keyed to the world's schema", async () => {
    const user = userEvent.setup();
    const dialog = await openCharacterCreator(user);

    // The Starting-stats "Propose" is the second ❖ Propose (Voice & tone sits above).
    await user.click(within(dialog).getAllByRole("button", { name: /❖ propose/i })[1]);
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
    await user.click(within(dialog).getByRole("button", { name: /draft with mytheca/i }));
    await waitFor(() =>
      expect(vi.mocked(api.draftCharacter)).toHaveBeenCalledWith(
        "A marsh-born scout.",
        expect.stringContaining("DOSSIER_MARKER"),
        expect.any(String),
      ),
    );
  });

  it("drafts from a Draft-tagged reference file alone (no seed sentence)", async () => {
    const user = userEvent.setup();
    const dialog = await openCharacterCreator(user);

    // With no seed typed, the Draft button is disabled.
    const draftBtn = within(dialog).getByRole("button", { name: /draft with mytheca/i });
    expect(draftBtn).toBeDisabled();

    // Dropping a Draft-tagged file (Draft toggle defaults ON) enables it.
    const file = new File(["Born of the salt marsh. DOCONLY_MARKER"], "lore.md", {
      type: "text/markdown",
    });
    await user.upload(within(dialog).getByLabelText(/browse files/i), file);
    await within(dialog).findByRole("button", { name: /remove lore\.md/i });
    expect(draftBtn).toBeEnabled();

    await user.click(draftBtn);
    await waitFor(() =>
      expect(vi.mocked(api.draftCharacter)).toHaveBeenCalledWith(
        "",
        expect.stringContaining("DOCONLY_MARKER"),
        expect.any(String),
      ),
    );
  });
});

describe("CharacterModal — save/delete busy state", () => {
  afterEach(() => vi.useRealTimers());

  it("disables Save/Delete immediately, but only shows the spinner past the delay gate", () => {
    vi.useFakeTimers();
    render(<CharacterModal lib={makeLib({ pending: true })} />);

    const save = screen.getByRole("button", { name: "Save Changes" });
    const del = screen.getByRole("button", { name: "Delete" });
    expect(save).toBeDisabled();
    expect(del).toBeDisabled();
    // Marked busy immediately — well before the spinner is shown.
    expect(save.closest("div")?.parentElement).toHaveAttribute("aria-busy", "true");
    expect(save).not.toHaveAttribute("aria-busy", "true");

    act(() => void vi.advanceTimersByTime(INDICATOR_DELAY_MS));
    expect(screen.getByRole("button", { name: "Saving character" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
    expect(screen.getByRole("button", { name: "Deleting character" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });

  it("shows the plain labels once the operation has resolved", () => {
    render(<CharacterModal lib={makeLib({ pending: false })} />);
    const save = screen.getByRole("button", { name: "Save Changes" });
    expect(save).toBeEnabled();
    expect(save).not.toHaveAttribute("aria-busy");
    expect(screen.getByRole("button", { name: "Delete" })).not.toHaveAttribute("aria-busy");
  });
});
