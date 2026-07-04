import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { CharacterCard } from "./CharacterCard";
import type { Character, StatDefinition } from "@/lib/types";

const base: Character = {
  id: "ren",
  name: "Ren",
  role: "Aspiring Warden Scout",
  color: "#A8762A",
  mono: "R",
  traits: "Energetic · Observant",
  speech: "Breathless.",
  goal: "Prove himself.",
  secret: "Lost the tracker.",
};

describe("CharacterCard", () => {
  it("renders the portrait when present and shows name + role", () => {
    render(
      <CharacterCard
        character={{ ...base, portrait: "/media/portraits/ren.webp" }}
        onPreview={() => {}}
      />,
    );
    expect(screen.getByAltText("Portrait of Ren")).toBeInTheDocument();
    expect(screen.getByText("Ren")).toBeInTheDocument();
    expect(screen.getByText("Aspiring Warden Scout")).toBeInTheDocument();
    // The whole card is a single "View" affordance.
    expect(screen.getByRole("button", { name: /view ren/i })).toBeInTheDocument();
  });

  it("falls back to the monogram when there is no portrait", () => {
    render(<CharacterCard character={base} onPreview={() => {}} />);
    expect(screen.queryByAltText(/portrait of/i)).not.toBeInTheDocument();
    expect(screen.getByText("R")).toBeInTheDocument();
  });

  it("shows the cast badge only when highlighted", () => {
    const { rerender } = render(<CharacterCard character={base} onPreview={() => {}} />);
    expect(screen.queryByText(/in this scene/i)).not.toBeInTheDocument();
    rerender(<CharacterCard character={base} onPreview={() => {}} highlighted />);
    expect(screen.getByText(/in this scene/i)).toBeInTheDocument();
  });

  it("glows in the character's own color only when highlighted", () => {
    const { container, rerender } = render(<CharacterCard character={base} onPreview={() => {}} />);
    const card = container.firstElementChild as HTMLElement;
    expect(card.className).not.toContain("velora-glow");
    expect(card.style.getPropertyValue("--glow-color")).toBe("");

    rerender(<CharacterCard character={base} onPreview={() => {}} highlighted />);
    expect(card.className).toContain("velora-glow");
    expect(card.style.getPropertyValue("--glow-color")).toBe(base.color);
  });

  it("calls onPreview on card click and onEdit on the pencil", async () => {
    const user = userEvent.setup();
    const onPreview = vi.fn();
    const onEdit = vi.fn();
    render(<CharacterCard character={base} onPreview={onPreview} onEdit={onEdit} />);
    await user.click(screen.getByRole("button", { name: /view ren/i }));
    expect(onPreview).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: /edit ren/i }));
    expect(onEdit).toHaveBeenCalledOnce();
  });
});

const STAT_DEFS: StatDefinition[] = [
  { key: "trust", displayName: "Trust", description: "", min: -10, max: 10, default: 0, visibility: "public", guidance: null, appliesTo: [], bands: [] },
  { key: "morale", displayName: "Morale", description: "", min: 0, max: 10, default: 5, visibility: "hidden", guidance: null, appliesTo: [], bands: [] },
];

describe("CharacterCard stats", () => {
  it("renders no stat rows when statDefs is omitted (back-compat)", () => {
    render(<CharacterCard character={base} onPreview={() => {}} />);
    expect(screen.queryByText("Trust")).not.toBeInTheDocument();
  });

  it("shows the real persisted value over the schema default", () => {
    render(
      <CharacterCard
        character={base}
        onPreview={() => {}}
        statDefs={STAT_DEFS}
        statValues={{ trust: 7 }}
      />,
    );
    expect(screen.getByText("Trust")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("falls back to the schema default for a stat never explicitly set", () => {
    render(<CharacterCard character={base} onPreview={() => {}} statDefs={STAT_DEFS} />);
    expect(screen.getByText("Trust")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("omits non-public stats", () => {
    render(<CharacterCard character={base} onPreview={() => {}} statDefs={STAT_DEFS} />);
    expect(screen.queryByText("Morale")).not.toBeInTheDocument();
  });
});
