import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { StorylineMenu } from "./StorylineMenu";
import type { Storyline } from "@/lib/types";

const STORYLINES: Storyline[] = [
  { id: "embergate", title: "Embergate", genre: "Maritime", tagline: "x", symbol: "★", symbolColor: "#2F7D6B", characters: [], settings: [], scenarios: [] },
  { id: "tidefall", title: "Tidefall", genre: "Naval", characters: [], settings: [], scenarios: [] },
];

function setup(storylines = STORYLINES) {
  const handlers = {
    onSwitch: vi.fn(),
    onCreate: vi.fn(),
    onEdit: vi.fn(),
    onConfigurePrompts: vi.fn(),
    onDocuments: vi.fn(),
    onDelete: vi.fn(),
  };
  render(<StorylineMenu storylines={storylines} activeId="embergate" {...handlers} />);
  return handlers;
}

describe("StorylineMenu", () => {
  it("offers Edit and Delete actions per storyline", async () => {
    const user = userEvent.setup();
    const { onEdit, onDelete } = setup();

    await user.click(screen.getByTitle(/switch storyline/i));
    await user.click(screen.getByRole("button", { name: /edit tidefall/i }));
    expect(onEdit).toHaveBeenCalledWith("tidefall");

    await user.click(screen.getByTitle(/switch storyline/i)); // reopen (closed on action)
    await user.click(screen.getByRole("button", { name: /delete embergate/i }));
    expect(onDelete).toHaveBeenCalledWith("embergate");
  });

  it("offers a per-storyline Documents action", async () => {
    const user = userEvent.setup();
    const { onDocuments } = setup();

    await user.click(screen.getByTitle(/switch storyline/i));
    await user.click(screen.getByRole("button", { name: /documents for tidefall/i }));
    expect(onDocuments).toHaveBeenCalledWith("tidefall");
  });

  it("offers a per-storyline writing-prompts (gear) action", async () => {
    const user = userEvent.setup();
    const { onConfigurePrompts } = setup();

    await user.click(screen.getByTitle(/switch storyline/i));
    await user.click(screen.getByRole("button", { name: /writing prompts for tidefall/i }));
    expect(onConfigurePrompts).toHaveBeenCalledWith("tidefall");
  });

  it("renders the active storyline's custom seal (symbol + color)", () => {
    setup();
    const seal = screen.getByText("★");
    expect(seal).toBeInTheDocument();
    expect(seal).toHaveStyle({ color: "#2F7D6B" });
  });

  it("falls back to the default diamond seal when none is set", async () => {
    const user = userEvent.setup();
    setup();
    // Tidefall has no symbol → the default ◆ shows on its dropdown row.
    await user.click(screen.getByTitle(/switch storyline/i));
    expect(screen.getAllByText("◆").length).toBeGreaterThan(0);
  });

  it("still switches storylines and creates a new one", async () => {
    const user = userEvent.setup();
    const { onSwitch, onCreate } = setup();

    await user.click(screen.getByTitle(/switch storyline/i));
    await user.click(screen.getByRole("button", { name: /^tidefall/i }));
    expect(onSwitch).toHaveBeenCalledWith("tidefall");

    await user.click(screen.getByTitle(/switch storyline/i));
    await user.click(screen.getByRole("button", { name: /new storyline/i }));
    expect(onCreate).toHaveBeenCalled();
  });

  it("shows counts from API count fields for non-hydrated storylines", async () => {
    const user = userEvent.setup();
    const storylines: Storyline[] = [
      {
        id: "embergate", title: "Embergate", genre: "Maritime",
        characters: [], settings: [], scenarios: [],
        scenarioCount: 3, characterCount: 5, settingCount: 2,
      },
      {
        id: "tidefall", title: "Tidefall", genre: "Naval",
        characters: [], settings: [], scenarios: [],
        scenarioCount: 1, characterCount: 4, settingCount: 7,
      },
    ];
    setup(storylines);
    await user.click(screen.getByTitle(/switch storyline/i));
    // Tidefall counts come from API fields, not from the empty arrays
    expect(screen.getByText(/1 scenario\b/)).toBeInTheDocument();
    expect(screen.getByText(/4 cast/)).toBeInTheDocument();
    expect(screen.getByText(/7 settings/)).toBeInTheDocument();
  });

  it("falls back to array length when API count fields are absent", async () => {
    const user = userEvent.setup();
    const storylines: Storyline[] = [
      {
        id: "embergate", title: "Embergate", genre: "Maritime",
        characters: [{ id: "c1", name: "A", role: "r", color: "#000", mono: "A", traits: "", speech: "", goal: "", secret: "" }],
        settings: [{ id: "s1", name: "S", type: "T", desc: "d" }],
        scenarios: [
          { id: "sc1", title: "Sc1", genre: "g", tone: "t", goal: "g", castIds: [], settingId: "s1", opening: "", branches: [] },
          { id: "sc2", title: "Sc2", genre: "g", tone: "t", goal: "g", castIds: [], settingId: "s1", opening: "", branches: [] },
        ],
        // No count fields — should fall back to array length
      },
    ];
    setup(storylines);
    await user.click(screen.getByTitle(/switch storyline/i));
    expect(screen.getByText(/2 scenarios/)).toBeInTheDocument();
    expect(screen.getByText(/1 cast/)).toBeInTheDocument();
    expect(screen.getByText(/1 setting\b/)).toBeInTheDocument();
  });
});
