import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { EntityModal } from "./EntityModal";
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
