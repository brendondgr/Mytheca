import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DirectorRail } from "./DirectorRail";
import { SEED_STAT_DEFS } from "@/lib/seed-data";
import type { StatDefinition } from "@/lib/types";

const props = {
  goal: "Find the smugglers.",
  tension: 60,
  tensionText: "Rising",
  statDefs: SEED_STAT_DEFS,
  stats: [{ label: "Suspicion", value: 2, kind: "neutral" as const }],
  relationships: [{ who: "Maerin", color: "#8E2B1C", text: "— answers to the Court." }],
};

describe("DirectorRail", () => {
  it("renders the storyline stat schema with default values + bands", () => {
    render(<DirectorRail {...props} />);
    expect(screen.getByText("Character stats")).toBeInTheDocument();
    expect(screen.getByText("Health")).toBeInTheDocument();
    expect(screen.getByText("Patience")).toBeInTheDocument();
    // Health default 100 sits in the "Very healthy" band (shown in the band legend).
    expect(screen.getByText("Very healthy")).toBeInTheDocument();
    // The current band's title is shown beside the stat name ("Health: Very healthy").
    expect(screen.getByText(": Very healthy")).toBeInTheDocument();
    // The "Very healthy" band's range is listed beside it.
    expect(screen.getByText("81–100")).toBeInTheDocument();
  });

  it("keeps the live Scene-state chips distinct from the schema", () => {
    render(<DirectorRail {...props} />);
    expect(screen.getByText("Scene state")).toBeInTheDocument();
    expect(screen.getByText("+2")).toBeInTheDocument();
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
    render(<DirectorRail {...props} statDefs={withHidden} />);
    expect(screen.queryByText("Morale")).not.toBeInTheDocument();
  });
});
