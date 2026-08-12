import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { act } from "react";
import { EntityModal } from "./EntityModal";
import { INDICATOR_DELAY_MS } from "@/hooks/use-delayed-flag";
import type { useLibraryState } from "@/features/library/useLibraryState";

type Lib = ReturnType<typeof useLibraryState>;

function makeLib(overrides: Partial<Lib> = {}): Lib {
  return {
    modal: { type: "scenario", mode: "agentic", editId: null },
    draft: {
      title: "The Salt Ledger",
      genre: "Intrigue",
      tone: "Tension · rising",
      goal: "Keep the ledger safe.",
      cast: [],
      settingId: "",
      branches: [],
      image: null,
      _sceneArtPositive: "",
      _sceneArtNegative: "",
      _ai: false,
      _docFiles: [],
    },
    isEditing: false,
    isValid: true,
    pending: false,
    generating: false,
    generatingPrompts: false,
    generatingPortrait: false,
    error: null,
    characters: [],
    settings: [],
    scenarios: [],
    setDraft: vi.fn(),
    setMode: vi.fn(),
    submit: vi.fn(),
    closeModal: vi.fn(),
    deleteEntity: vi.fn(),
    draftScenario: vi.fn(),
    generateScenarioSceneArtPrompts: vi.fn(),
    generateScenarioSceneArt: vi.fn(),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any as Lib;
}

describe("EntityModal (scenario)", () => {
  it("renders the scenario form and agentic aside when modal.type is scenario", () => {
    render(<EntityModal lib={makeLib()} />);
    expect(screen.getByText("New Scenario")).toBeInTheDocument();
    // Scene art section is visible in the aside
    expect(screen.getByText("Scene art")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /edit image/i })).toBeInTheDocument();
  });

  it("shows the scene-art placeholder when draft.image is null", () => {
    render(<EntityModal lib={makeLib()} />);
    expect(screen.getByText("No scene art yet")).toBeInTheDocument();
  });

  it("shows the rendered image when draft.image is set", () => {
    const lib = makeLib();
    lib.draft = { ...lib.draft, image: "/media/scenes/abc.webp" };
    render(<EntityModal lib={lib} />);
    const img = screen.getByAltText(/scene art for/i);
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute("src", expect.stringContaining("abc.webp"));
  });

  it("opens the SceneArtModal when Edit image is clicked", () => {
    render(<EntityModal lib={makeLib()} />);
    fireEvent.click(screen.getByRole("button", { name: /edit image/i }));
    // SceneArtModal title should appear
    expect(screen.getByText("Scene art", { selector: "[id='scene-art-modal-title']" })).toBeInTheDocument();
  });

  it("renders nothing when modal is not a scenario", () => {
    const lib = makeLib();
    lib.modal = { type: "setting", mode: "manual", editId: null };
    const { container } = render(<EntityModal lib={lib} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the ContextFilesPanel context files section in agentic mode", () => {
    render(<EntityModal lib={makeLib()} />);
    // Eyebrow renders "⎙ Context files" — use regex; browse-files is a <label>
    expect(screen.getByText(/context files/i)).toBeInTheDocument();
    expect(screen.getByText("Browse files")).toBeInTheDocument();
  });

  it("hides the ContextFilesPanel in manual mode on small screens", () => {
    const lib = makeLib();
    lib.modal = { type: "scenario", mode: "manual", editId: null };
    render(<EntityModal lib={lib} />);
    // The panel uses `hidden md:flex` when show=false — confirm the aside carries hidden
    const aside = screen.getByText(/context files/i).closest("aside");
    expect(aside).toHaveClass("hidden");
  });
});

describe("EntityModal — save/delete busy state", () => {
  afterEach(() => vi.useRealTimers());

  it("disables Save/Delete immediately, but only shows the spinner past the delay gate", () => {
    vi.useFakeTimers();
    // makeLib() ignores its `overrides` param (pre-existing) — set fields directly,
    // matching this file's existing convention (see `lib.modal = …` above).
    const lib = makeLib();
    lib.isEditing = true;
    lib.pending = true;
    lib.modal = { type: "scenario", mode: "manual", editId: "sc-1" };
    render(<EntityModal lib={lib} />);

    const save = screen.getByRole("button", { name: "Save Changes" });
    const del = screen.getByRole("button", { name: "Delete" });
    expect(save).toBeDisabled();
    expect(del).toBeDisabled();
    expect(save).not.toHaveAttribute("aria-busy", "true");

    act(() => void vi.advanceTimersByTime(INDICATOR_DELAY_MS));
    expect(screen.getByRole("button", { name: "Saving scenario" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
    expect(screen.getByRole("button", { name: "Deleting scenario" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });

  it("shows the plain labels once the operation has resolved", () => {
    const lib = makeLib();
    lib.isEditing = true;
    lib.modal = { type: "scenario", mode: "manual", editId: "sc-1" };
    render(<EntityModal lib={lib} />);
    expect(screen.getByRole("button", { name: "Save Changes" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Delete" })).not.toHaveAttribute("aria-busy");
  });
});
