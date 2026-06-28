import { render, screen, fireEvent, within } from "@testing-library/react";
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

  it("renders each cast member's name and role (no always-on statistics)", () => {
    renderCarousel();
    expect(screen.getByText("Hunter Krow")).toBeInTheDocument();
    expect(screen.getByText("Warden Hunter")).toBeInTheDocument();
    expect(screen.getByText("Ren")).toBeInTheDocument();
    // Statistics are hidden behind the per-card arrow — none shown initially.
    expect(screen.queryByText("Statistics")).toBeNull();
  });

  it("toggles an inline statistics panel from a per-card arrow (one open at a time)", async () => {
    const user = userEvent.setup();
    renderCarousel();
    await user.click(screen.getByRole("button", { name: /show statistics for hunter krow/i }));
    expect(screen.getByRole("region", { name: /hunter krow statistics/i })).toBeInTheDocument();
    expect(screen.getByText(/no statistics available/i)).toBeInTheDocument();
    // Opening another card's panel closes the first.
    await user.click(screen.getByRole("button", { name: /show statistics for ren/i }));
    expect(screen.getByRole("region", { name: /ren statistics/i })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /hunter krow statistics/i })).toBeNull();
    // Clicking the open card's arrow again closes it.
    await user.click(screen.getByRole("button", { name: /hide statistics for ren/i }));
    expect(screen.queryByRole("region", { name: /ren statistics/i })).toBeNull();
  });

  it("lists the storyline's public stat names + defaults in the panel", async () => {
    const user = userEvent.setup();
    renderCarousel({
      statDefs: [
        { key: "resolve", displayName: "Resolve", description: "", min: 0, max: 10, default: 7, visibility: "public", guidance: null, appliesTo: [], bands: [] },
        { key: "secrecy", displayName: "Secrecy", description: "", min: 0, max: 10, default: 4, visibility: "hidden", guidance: null, appliesTo: [], bands: [] },
      ],
    });
    await user.click(screen.getByRole("button", { name: /show statistics for hunter krow/i }));
    const region = screen.getByRole("region", { name: /hunter krow statistics/i });
    expect(within(region).getByText("Resolve")).toBeInTheDocument();
    expect(within(region).getByText("7")).toBeInTheDocument();
    // Hidden-visibility stats are omitted from the player view.
    expect(within(region).queryByText("Secrecy")).toBeNull();
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

  it("renders each cast card as a discrete rounded, transparent tile", () => {
    const { container } = renderWithContainer();
    // Each card is a rounded, gapped tile (no flush border-r dividers).
    expect(container.querySelectorAll(".group.rounded-\\[6px\\]").length).toBe(2);
    // Cards are transparent — no always-on solid Statistics block.
    expect(screen.queryByText("Statistics")).toBeNull();
  });

  it("hides the cast carousel arrows when the cast fits within the strip", () => {
    // jsdom reports zero layout, so scrollWidth === clientWidth → no overflow.
    renderCarousel();
    expect(screen.queryByRole("button", { name: /next characters/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /previous characters/i })).toBeNull();
  });

  it("shows arrow controls and pages the cast strip when it overflows", async () => {
    const user = userEvent.setup();
    const { container } = renderWithContainer();
    const strip = container.querySelector(".overflow-x-auto") as HTMLElement;
    const scrollBy = vi.fn();
    strip.scrollBy = scrollBy;

    // At the start of an overflowing strip: only the Next arrow shows.
    forceStripMetrics(strip, 0);
    const next = screen.getByRole("button", { name: /next characters/i });
    expect(screen.queryByRole("button", { name: /previous characters/i })).toBeNull();
    await user.click(next);
    expect(scrollBy).toHaveBeenCalled();
    expect(scrollBy.mock.calls[0][0].left).toBeGreaterThan(0);

    // Scrolled to the end: only the Previous arrow shows.
    forceStripMetrics(strip, 800);
    expect(screen.getByRole("button", { name: /previous characters/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /next characters/i })).toBeNull();
  });
});

/** Force a scroll container's layout metrics (jsdom reports 0) and fire scroll. */
function forceStripMetrics(strip: HTMLElement, scrollLeft: number, scrollWidth = 1200, clientWidth = 400) {
  Object.defineProperty(strip, "scrollWidth", { configurable: true, value: scrollWidth });
  Object.defineProperty(strip, "clientWidth", { configurable: true, value: clientWidth });
  Object.defineProperty(strip, "scrollLeft", { configurable: true, writable: true, value: scrollLeft });
  fireEvent.scroll(strip);
}

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
