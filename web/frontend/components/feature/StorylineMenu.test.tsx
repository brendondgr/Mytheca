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
    // The seal's colour is an ENTITY colour: theme-independent and chosen for
    // identity, so it is carried as `--entity` and rendered through
    // `text-entity`, which mixes it toward the active theme's ink. Applied raw
    // it measured as low as 1.71:1 in the baseline audit.
    expect(seal.style.getPropertyValue("--entity")).toBe("#2F7D6B");
    expect(seal.className).toContain("text-entity");
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

describe("StorylineMenu at the narrow floor", () => {
  it("names the active world even when its title is not drawn", () => {
    // Below `md` the title span is hidden and the seal + caret carry the control visually.
    // The accessible name has to stay complete — "Switch storyline" alone does not say
    // which world is open.
    setup();
    expect(
      screen.getByRole("button", { name: "Switch storyline — Embergate" }),
    ).toBeInTheDocument();
  });

  it("falls back to a bare name when there is no storyline at all", () => {
    setup([]);
    expect(screen.getByRole("button", { name: "Switch storyline" })).toBeInTheDocument();
  });

  it("hides the title in CSS, not by removing it — one DOM copy, no hydration swap", () => {
    setup();
    const title = screen.getByText("Embergate", { selector: "span" });
    expect(title.className).toContain("hidden");
    expect(title.className).toContain("md:inline");
  });

  it("switches worlds from the narrow trigger", async () => {
    const user = userEvent.setup();
    const { onSwitch } = setup();
    await user.click(screen.getByRole("button", { name: "Switch storyline — Embergate" }));
    // The row's own button, not the per-row edit/documents/prompt actions that also name it.
    await user.click(screen.getByRole("button", { name: /^Tidefall/ }));
    expect(onSwitch).toHaveBeenCalledWith("tidefall");
  });

  it("pins the popover to the viewport below md, so it cannot overhang", async () => {
    // Measured at 320: the trigger sits 203px from the left, so an `absolute left-0` panel
    // runs from 203 to 483 no matter how narrow it is told to be. Capping the width does
    // nothing; anchoring to the viewport is the only form that cannot overhang.
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: "Switch storyline — Embergate" }));
    const panel = screen.getByText("Storylines").parentElement!;
    expect(panel.className).toContain("fixed");
    expect(panel.className).toContain("inset-x-[12px]");
    // ...and the desktop geometry is unchanged.
    expect(panel.className).toContain("md:absolute");
    expect(panel.className).toContain("md:left-0");
    expect(panel.className).toContain("md:w-[280px]");
  });

  it("scrolls inside itself rather than running off the bottom", async () => {
    // Measured at 320 against a real library: 4912px tall. `fixed` means the page cannot
    // scroll it into view, so without this every world past the first few is unreachable.
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: "Switch storyline — Embergate" }));
    const panel = screen.getByText("Storylines").parentElement!;
    expect(panel.className).toContain("overflow-y-auto");
    expect(panel.className).toContain("max-h-[calc(100dvh-70px)]");
  });
});
