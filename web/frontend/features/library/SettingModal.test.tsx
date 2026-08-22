import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach } from "vitest";
import { act } from "react";
import { LibraryView } from "./LibraryView";
import { SettingModal } from "@/components/feature/SettingModal";
import { INDICATOR_DELAY_MS } from "@/hooks/use-delayed-flag";
import type { useLibraryState } from "@/features/library/useLibraryState";
import * as api from "@/lib/api";

type Lib = ReturnType<typeof useLibraryState>;

function makeLib(overrides: Partial<Lib> = {}): Lib {
  return {
    modal: { type: "setting", mode: "manual", editId: "s-1" },
    draft: { name: "The Lantern Quay", type: "Social Hub" },
    isValid: true,
    pending: false,
    generating: false,
    generatingPrompts: false,
    generatingPortrait: false,
    error: null,
    activeField: null,
    setDraft: vi.fn(),
    setMode: vi.fn(),
    closeModal: vi.fn(),
    submit: vi.fn(),
    deleteEntity: vi.fn(),
    draftSetting: vi.fn(),
    generateSceneArtPrompts: vi.fn(),
    generateSceneArt: vi.fn(),
    ...overrides,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any as Lib;
}

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

async function openSettingCreator(user: ReturnType<typeof userEvent.setup>) {
  render(<LibraryView />);
  await screen.findAllByText("The Embergate Conspiracy");
  await user.click(screen.getByRole("button", { name: /\+ create/i }));
  await user.click(screen.getByRole("button", { name: /add a setting/i }));
  return screen.getByRole("dialog");
}

describe("SettingModal — agentic creator", () => {
  // 15s, not the 5s default: this waits on the ~150ms-per-field choreographed reveal, so a
  // busy machine blows the budget while the component is behaving correctly. Documented in
  // docs/checklist.md as a load flake; the prescribed fix is the timeout, not the assertions.
  it("drafts a full setting from a seed into the form", { timeout: 15_000 }, async () => {
    const user = userEvent.setup();
    const dialog = await openSettingCreator(user);

    await user.type(
      within(dialog).getByLabelText(/describe the place to draft/i),
      "A flooded smugglers' market.",
    );
    const draftBtn = within(dialog).getByRole("button", { name: /draft with mytheca/i });
    expect(draftBtn).toBeEnabled();
    await user.click(draftBtn);

    expect(vi.mocked(api.draftSetting)).toHaveBeenCalled();
    // Fields fill in one at a time (choreographed reveal) — wait for the last.
    await waitFor(() =>
      expect(within(dialog).getByLabelText(/^name$/i)).toHaveValue("Drafted Place"),
    );
    await waitFor(() => {
      expect(within(dialog).getByLabelText(/atmosphere & senses/i)).toHaveValue(
        "A drafted atmosphere.",
      );
      expect(within(dialog).getByLabelText(/notable features/i)).toHaveValue("Drafted features.");
      expect(within(dialog).getByLabelText(/current state/i)).toHaveValue(
        "A drafted current state.",
      );
    });
  });

  // Same real-time bound as the test above and as `CharacterModal.test.tsx`: this awaits the
  // ~150ms-per-field `use-field-reveal` choreography, which alone runs past Vitest's 5s
  // default once the suite is under full worker concurrency. The test is correct; the budget
  // was too tight. Raised here rather than globally, so the next genuinely-hung test still
  // fails fast.
  it("shows draft progress and highlights the field being written", { timeout: 15_000 }, async () => {
    const user = userEvent.setup();
    const dialog = await openSettingCreator(user);

    await user.type(
      within(dialog).getByLabelText(/describe the place to draft/i),
      "A flooded smugglers' market.",
    );
    await user.click(within(dialog).getByRole("button", { name: /draft with mytheca/i }));

    expect(
      await within(dialog).findByRole("group", { name: /setting draft progress/i }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(dialog.querySelector(".mytheca-field-active")).not.toBeNull();
    });
  });

  it("generates scene-art prompts, then renders an establishing image", async () => {
    const user = userEvent.setup();
    const dialog = await openSettingCreator(user);

    // A description enables "Generate prompts". The scene-art flow lives in a
    // pop-up reached from the compact preview's "Edit image" button.
    await user.type(within(dialog).getByLabelText(/atmosphere & senses/i), "A drowned chapel.");
    await user.click(within(dialog).getByRole("button", { name: /edit image/i }));
    const sceneArt = screen.getByRole("dialog", { name: /^scene art$/i });

    await user.click(within(sceneArt).getByRole("button", { name: /generate prompts/i }));
    await waitFor(() => {
      const positive = within(sceneArt).getByLabelText(
        /scene-art positive prompt/i,
      ) as HTMLTextAreaElement;
      expect(positive.value).toContain("watercolor");
    });

    // Rendering the image calls ComfyUI and shows the WebP preview.
    await user.click(within(sceneArt).getByRole("button", { name: /generate scene art/i }));
    expect(vi.mocked(api.generateSceneArt)).toHaveBeenCalledWith(
      expect.objectContaining({ positive: expect.stringContaining("watercolor") }),
    );
    await waitFor(() =>
      expect(screen.getAllByAltText(/establishing image of/i).length).toBeGreaterThan(0),
    );
  });

  it("creates a setting with its node metadata", async () => {
    const user = userEvent.setup();
    const dialog = await openSettingCreator(user);

    await user.type(within(dialog).getByLabelText(/^name$/i), "The Lantern Quay");
    await user.type(
      within(dialog).getByLabelText(/atmosphere & senses/i),
      "Swaying lights over black water.",
    );
    const submit = within(dialog).getByRole("button", { name: /add setting/i });
    expect(submit).toBeEnabled();
    await user.click(submit);

    expect(vi.mocked(api.createSetting)).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        name: "The Lantern Quay",
        atmosphere: "Swaying lights over black water.",
      }),
    );
    expect(await screen.findByText("The Lantern Quay")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("grounds the draft with a dropped reference file's text", async () => {
    const user = userEvent.setup();
    const dialog = await openSettingCreator(user);

    const file = new File(["Built on a sunken reef. GAZETTEER_MARKER"], "gazetteer.md", {
      type: "text/markdown",
    });
    await user.upload(within(dialog).getByLabelText(/browse files/i), file);
    expect(
      await within(dialog).findByRole("button", { name: /remove gazetteer\.md/i }),
    ).toBeInTheDocument();

    await user.type(
      within(dialog).getByLabelText(/describe the place to draft/i),
      "A reef-built harbor.",
    );
    await user.click(within(dialog).getByRole("button", { name: /draft with mytheca/i }));
    await waitFor(() =>
      expect(vi.mocked(api.draftSetting)).toHaveBeenCalledWith(
        "A reef-built harbor.",
        expect.stringContaining("GAZETTEER_MARKER"),
        expect.any(String),
      ),
    );
  });

  it("drafts from a Draft-tagged reference file alone (no seed sentence)", async () => {
    const user = userEvent.setup();
    const dialog = await openSettingCreator(user);

    // With no seed typed, the Draft button is disabled.
    const draftBtn = within(dialog).getByRole("button", { name: /draft with mytheca/i });
    expect(draftBtn).toBeDisabled();

    // Dropping a Draft-tagged file (Draft toggle defaults ON) enables it.
    const file = new File(["Built on a sunken reef. DOCONLY_MARKER"], "lore.md", {
      type: "text/markdown",
    });
    await user.upload(within(dialog).getByLabelText(/browse files/i), file);
    await within(dialog).findByRole("button", { name: /remove lore\.md/i });
    expect(draftBtn).toBeEnabled();

    await user.click(draftBtn);
    await waitFor(() =>
      expect(vi.mocked(api.draftSetting)).toHaveBeenCalledWith(
        "",
        expect.stringContaining("DOCONLY_MARKER"),
        expect.any(String),
      ),
    );
  });
});

describe("SettingModal — save/delete busy state", () => {
  afterEach(() => vi.useRealTimers());

  it("disables Save/Delete immediately, but only shows the spinner past the delay gate", () => {
    vi.useFakeTimers();
    render(<SettingModal lib={makeLib({ pending: true })} />);

    const save = screen.getByRole("button", { name: "Save Changes" });
    const del = screen.getByRole("button", { name: "Delete" });
    expect(save).toBeDisabled();
    expect(del).toBeDisabled();
    expect(save).not.toHaveAttribute("aria-busy", "true");

    act(() => void vi.advanceTimersByTime(INDICATOR_DELAY_MS));
    expect(screen.getByRole("button", { name: "Saving setting" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
    expect(screen.getByRole("button", { name: "Deleting setting" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });

  it("shows the plain labels once the operation has resolved", () => {
    render(<SettingModal lib={makeLib({ pending: false })} />);
    expect(screen.getByRole("button", { name: "Save Changes" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Delete" })).not.toHaveAttribute("aria-busy");
  });
});
