import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { CharacterDossier } from "./CharacterDossier";
import { SEED_STAT_DEFS } from "@/lib/seed-data";
import type { Character, StatDefinition } from "@/lib/types";
import type { StatChip } from "@/features/story-player/scene-data";

const MAERIN: Character = {
  id: "maerin",
  name: "Maerin",
  role: "Broker",
  color: "#8E2B1C",
  mono: "M",
  traits: "",
  speech: "",
} as Character;

function renderDossier(stats?: StatChip[], statDefs: StatDefinition[] = SEED_STAT_DEFS) {
  return render(
    <CharacterDossier
      character={MAERIN}
      statDefs={statDefs}
      stats={stats}
      relationships={[]}
      onClose={vi.fn()}
      onOpenProfile={vi.fn()}
    />,
  );
}

describe("CharacterDossier stats", () => {
  it("shows schema defaults when the character has no live stats yet", () => {
    renderDossier(undefined);
    // Health default 100 → "Very healthy" band beside the name.
    expect(screen.getByText(": Very healthy")).toBeInTheDocument();
  });

  it("reflects a character's live stat value (band + readout move)", () => {
    // A wounding drops Health to 30 for THIS character.
    renderDossier([{ label: "Health", value: 30 }]);
    // The band beside the name follows the live value (21–40 → "Badly hurt…").
    expect(screen.getByText(": Badly hurt — needs to heal")).toBeInTheDocument();
    expect(screen.getByText("30")).toBeInTheDocument();
    // The default band title is no longer shown for Health.
    expect(screen.queryByText(": Very healthy")).not.toBeInTheDocument();
  });

  it("opens the band legend showing each range beside its label", async () => {
    renderDossier(undefined);
    screen.getByRole("button", { name: "What Health ranges mean" }).click();
    expect(await screen.findByText("81–100")).toBeInTheDocument();
  });

  it("omits non-public stats from the schema panel", () => {
    const withHidden: StatDefinition[] = [
      ...SEED_STAT_DEFS,
      {
        key: "morale",
        displayName: "Morale",
        description: "hidden",
        min: 0,
        max: 10,
        default: 5,
        visibility: "hidden",
        guidance: null,
        appliesTo: [],
        bands: [],
      },
    ];
    renderDossier(undefined, withHidden);
    expect(screen.queryByText("Morale")).not.toBeInTheDocument();
  });
});

describe("CharacterDossier — how they speak", () => {
  it("shows the word-choice setting read-only, in words", () => {
    render(
      <CharacterDossier
        character={{ ...MAERIN, speech: "Clipped, never repeats herself.", looseness: -2 } as Character}
        statDefs={SEED_STAT_DEFS}
        relationships={[]}
        onClose={vi.fn()}
        onOpenProfile={vi.fn()}
      />,
    );
    expect(screen.getByText(/clipped, never repeats herself/i)).toBeInTheDocument();
    expect(screen.getByText(/word choice · Controlled/i)).toBeInTheDocument();
  });

  it("offers no way to change it — editing mid-play is a deferral, not an oversight", () => {
    render(
      <CharacterDossier
        character={{ ...MAERIN, looseness: 1 } as Character}
        statDefs={SEED_STAT_DEFS}
        relationships={[]}
        onClose={vi.fn()}
        onOpenProfile={vi.fn()}
      />,
    );
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
  });

  it("says nothing when the character has neither a speech style nor a setting", () => {
    render(
      <CharacterDossier
        character={MAERIN}
        statDefs={SEED_STAT_DEFS}
        relationships={[]}
        onClose={vi.fn()}
        onOpenProfile={vi.fn()}
      />,
    );
    expect(screen.queryByText(/how they speak/i)).not.toBeInTheDocument();
  });
});
