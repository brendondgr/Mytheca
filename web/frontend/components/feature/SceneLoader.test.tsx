import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { SceneLoader } from "./SceneLoader";
import {
  resolveScenario,
  SEED_CHARACTERS,
  SEED_SCENARIOS,
  SEED_SETTINGS,
} from "@/lib/seed-data";

const embergate = resolveScenario(
  SEED_SCENARIOS[0],
  SEED_CHARACTERS,
  SEED_SETTINGS,
);

describe("SceneLoader", () => {
  it("renders nothing when not visible", () => {
    const { container } = render(
      <SceneLoader scenario={embergate} visible={false} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the scenario's establishing context (title, setting, cast, goal)", () => {
    render(
      <SceneLoader scenario={embergate} storylineName="Embergate" visible />,
    );
    // A labelled status region for the loading state.
    expect(
      screen.getByRole("status", { name: /loading the scene/i }),
    ).toBeInTheDocument();
    // Storyline kicker + scenario title.
    expect(screen.getByText(/Entering Embergate/i)).toBeInTheDocument();
    expect(screen.getByText("The Embergate Conspiracy")).toBeInTheDocument();
    // Setting + genre/tone.
    expect(screen.getByText(/The Saltworn Tavern/)).toBeInTheDocument();
    expect(screen.getByText(/Intrigue/)).toBeInTheDocument();
    // The cast gathers (first cast member shown).
    expect(screen.getByText("Maerin Voss")).toBeInTheDocument();
    // The scene goal.
    expect(screen.getByText(/Uncover who smuggles/i)).toBeInTheDocument();
    // The conjuring progress line.
    expect(screen.getByText(/Conjuring the scene/i)).toBeInTheDocument();
  });

  it("falls back to a generic kicker without a storyline name", () => {
    render(<SceneLoader scenario={embergate} visible />);
    expect(screen.getByText(/Entering the scene/i)).toBeInTheDocument();
  });
});
