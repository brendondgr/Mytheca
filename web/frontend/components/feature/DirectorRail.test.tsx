import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DirectorRail } from "./DirectorRail";

const props = {
  goal: "Find the smugglers.",
  tension: 60,
  tensionText: "Rising",
  stats: [{ label: "Suspicion", value: 2, kind: "neutral" as const }],
  relationships: [{ who: "Maerin", color: "#8E2B1C", text: "— answers to the Court." }],
};

describe("DirectorRail", () => {
  it("keeps the live Scene-state chips + relationships (no per-character stat block)", () => {
    render(<DirectorRail {...props} />);
    expect(screen.getByText("Scene state")).toBeInTheDocument();
    expect(screen.getByText("+2")).toBeInTheDocument();
    expect(screen.getByText("Relationships")).toBeInTheDocument();
    // The un-wired, always-schema-default "Character stats" legend was removed — per-character
    // stats now live in the cast rail (beneath each name) and the character dossier instead.
    expect(screen.queryByText("Character stats")).not.toBeInTheDocument();
  });
});
