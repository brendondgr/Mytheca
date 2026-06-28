import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ScenarioCarousel } from "./ScenarioCarousel";
import type { Character, ResolvedScenario } from "@/lib/types";

const krow: Character = {
  id: "c1",
  name: "Hunter Krow",
  role: "Warden Hunter",
  color: "#2F7D6B",
  mono: "HK",
  traits: "Rugged · Solitary",
  speech: "Clipped.",
  goal: "Survive.",
  secret: "Knows the way out.",
  portrait: "/media/portraits/krow.webp",
};

const ren: Character = {
  id: "c2",
  name: "Ren",
  role: "Aspiring Scout",
  color: "#A8762A",
  mono: "R",
  traits: "Eager · Quick",
  speech: "Bright.",
  goal: "Prove herself.",
  secret: "Afraid of the dark.",
  portrait: null, // no portrait → monogram fallback
};

const scenario: ResolvedScenario = {
  id: "sc1",
  title: "The Silent Hunt",
  genre: "Survival",
  tone: "Tension · eerie",
  goal: "Locate the lost survey cache before the sound-predators arrive.",
  castIds: ["c1", "c2"],
  settingId: "s1",
  opening: "Wind-scoured ice stretches to the horizon.",
  branches: [],
  image: "/media/scenes/tundra.webp",
  cast: [krow, ren],
  setting: { id: "s1", name: "The Ghost-Echo Tundra", type: "Exploration", desc: "Cold." },
};

function renderCarousel(overrides: Partial<Parameters<typeof ScenarioCarousel>[0]> = {}) {
  const props = {
    slides: [scenario],
    index: 0,
    onPrev: vi.fn(),
    onNext: vi.fn(),
    onSelect: vi.fn(),
    counterText: "1 / 1",
    onBegin: vi.fn(),
    onProfile: vi.fn(),
    ...overrides,
  };
  render(<ScenarioCarousel {...props} />);
  return props;
}

describe("ScenarioCarousel", () => {
  it("renders the empty state when there are no slides", () => {
    render(
      <ScenarioCarousel
        slides={[]}
        index={0}
        onPrev={vi.fn()}
        onNext={vi.fn()}
        onSelect={vi.fn()}
        counterText="0 / 0"
      />,
    );
    expect(screen.getByText(/no scenarios yet/i)).toBeInTheDocument();
  });

  it("renders the scenario title, location, and a Begin Scene action", async () => {
    const user = userEvent.setup();
    const { onBegin } = renderCarousel();
    expect(screen.getByRole("heading", { name: "The Silent Hunt" })).toBeInTheDocument();
    expect(screen.getByText(/the ghost-echo tundra/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /begin scene/i }));
    expect(onBegin).toHaveBeenCalledWith("sc1");
  });

  it("renders each cast member's name, role, and the statistics empty state", () => {
    renderCarousel();
    expect(screen.getByText("Hunter Krow")).toBeInTheDocument();
    expect(screen.getByText("Warden Hunter")).toBeInTheDocument();
    expect(screen.getByText("Ren")).toBeInTheDocument();
    // One "Statistics" eyebrow + empty-state line per cast member.
    expect(screen.getAllByText("Statistics")).toHaveLength(2);
    expect(screen.getAllByText(/no statistics available/i)).toHaveLength(2);
  });

  it("shows a full-bleed portrait image when the character has one", () => {
    const { container } = renderWithContainer();
    const portrait = container.querySelector('img[src*="krow.webp"]');
    expect(portrait).not.toBeNull();
    expect(portrait).toHaveClass("object-cover");
  });

  it("falls back to a monogram (no portrait img) when the character has none", () => {
    const { container } = renderWithContainer();
    // Cast portraits carry `object-top` (the scene-art image does not), so this
    // counts only cast portraits: Krow has one, Ren falls back (no portrait img).
    expect(container.querySelectorAll("img.object-top").length).toBe(1);
  });

  it("opens the character profile when a cast card is clicked", async () => {
    const user = userEvent.setup();
    const { onProfile } = renderCarousel();
    await user.click(screen.getByRole("button", { name: "View Hunter Krow" }));
    expect(onProfile).toHaveBeenCalledWith("c1");
  });

  it("wires the previous/next controls", async () => {
    const user = userEvent.setup();
    const { onPrev, onNext } = renderCarousel();
    await user.click(screen.getByRole("button", { name: /previous scenario/i }));
    await user.click(screen.getByRole("button", { name: /next scenario/i }));
    expect(onPrev).toHaveBeenCalledTimes(1);
    expect(onNext).toHaveBeenCalledTimes(1);
  });
});

// Helper that also returns the container for DOM-level (decorative img) queries.
function renderWithContainer() {
  return render(
    <ScenarioCarousel
      slides={[scenario]}
      index={0}
      onPrev={vi.fn()}
      onNext={vi.fn()}
      onSelect={vi.fn()}
      counterText="1 / 1"
      onBegin={vi.fn()}
      onProfile={vi.fn()}
    />,
  );
}
