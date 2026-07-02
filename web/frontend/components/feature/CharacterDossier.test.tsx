import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { CharacterDossier } from "./CharacterDossier";
import { SEED_STAT_DEFS } from "@/lib/seed-data";
import type { Character } from "@/lib/types";
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

function renderDossier(stats?: StatChip[]) {
  return render(
    <CharacterDossier
      character={MAERIN}
      statDefs={SEED_STAT_DEFS}
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
});
