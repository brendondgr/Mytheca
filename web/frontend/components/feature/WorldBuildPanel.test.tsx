import { render, screen, within } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { WorldBuildPanel } from "./WorldBuildPanel";
import type { ProposedCharacter, ProposedSetting, ProposedWorld } from "@/lib/types";

function character(over: Partial<ProposedCharacter> = {}): ProposedCharacter {
  return {
    name: "Maerin",
    role: "Smuggler",
    traits: "Wary",
    speech: "Clipped.",
    goal: "Out.",
    secret: "Informant.",
    appearance: "Weathered.",
    background: "Dockborn.",
    personality: "Guarded.",
    color: "#3A5A78",
    voiceSamples: [],
    startingStats: [],
    ...over,
  };
}

function setting(over: Partial<ProposedSetting> = {}): ProposedSetting {
  return {
    name: "The Quay",
    type: "Social Hub",
    desc: "Lamplit.",
    atmosphere: "Brine.",
    features: "Lanterns.",
    currentState: "Open.",
    ...over,
  };
}

function world(over: Partial<ProposedWorld> = {}): ProposedWorld {
  return {
    storyline: { title: "Embergate", genre: "Intrigue", tagline: "", premise: "", worldPrimer: "" },
    stats: [],
    characters: [],
    settings: [],
    ...over,
  };
}

const noop = () => {};
const baseProps = {
  onUpdateCharacter: noop,
  onRemoveCharacter: noop,
  onUpdateSetting: noop,
  onRemoveSetting: noop,
  onDiscard: noop,
  imagesAvailable: false,
  generateImages: false,
  onToggleImages: noop,
};

describe("WorldBuildPanel", () => {
  it("shows the stage + skeleton cards for not-yet-drafted concepts while building", () => {
    render(
      <WorldBuildPanel
        {...baseProps}
        building
        buildStage="Drafting character 2 of 2…"
        planConcepts={{ characters: ["A wary smuggler.", "A cold inquisitor."], settings: ["A drowned chapel."] }}
        proposed={world({ characters: [character({ name: "Maerin" })] })}
      />,
    );
    expect(screen.getByText("Drafting character 2 of 2…")).toBeInTheDocument();
    // The drafted character shows read-only (no name textbox) during the build…
    expect(screen.getByText("Maerin")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /character 1 name/i })).not.toBeInTheDocument();
    // …and the remaining concepts render as "Drafting…" skeletons (1 char + 1 setting).
    expect(screen.getAllByText(/drafting…/i)).toHaveLength(2);
    expect(screen.getByText("A cold inquisitor.")).toBeInTheDocument();
  });

  it("becomes the editable review with controls once the build completes", () => {
    const onToggleImages = vi.fn();
    render(
      <WorldBuildPanel
        {...baseProps}
        building={false}
        buildStage={null}
        planConcepts={null}
        imagesAvailable
        generateImages
        onToggleImages={onToggleImages}
        proposed={world({ characters: [character()], settings: [setting()] })}
      />,
    );
    const region = screen.getByRole("region", { name: /proposed world/i });
    expect(within(region).getByDisplayValue("Maerin")).toBeInTheDocument();
    expect(within(region).getByDisplayValue("The Quay")).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: /remove maerin/i })).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: /discard/i })).toBeInTheDocument();
    expect(within(region).getByRole("checkbox")).toBeChecked();
  });

  it("renders portrait + scene-art previews when present", () => {
    render(
      <WorldBuildPanel
        {...baseProps}
        building={false}
        buildStage={null}
        planConcepts={null}
        proposed={world({
          characters: [character({ name: "Maerin", portrait: "/media/portraits/m.webp" })],
          settings: [setting({ name: "The Quay", image: "/media/scenes/q.webp" })],
        })}
      />,
    );
    expect(screen.getByAltText("Maerin portrait")).toBeInTheDocument();
    expect(screen.getByAltText("The Quay scene art")).toBeInTheDocument();
  });
});
