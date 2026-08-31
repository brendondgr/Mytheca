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
    onBegin: vi.fn(),
    onProfile: vi.fn(),
    ...overrides,
  };
  render(<ScenarioCarousel {...props} />);
  return props;
}

describe("ScenarioCarousel — the hero as a scroll track", () => {
  it("is a snap track, so a finger can move it", () => {
    const { container } = renderWithContainer();
    const track = container.querySelector(".scroll-track")!;
    // The pager it replaced was a `translateX` on a parent: swipe, click-drag, the
    // trackpad, the arrow keys and a screen reader's own scrolling all had no answer.
    expect(track.className).toContain("snap-x");
    expect(track.className).toContain("overflow-x-auto");
    expect((track as HTMLElement).style.transform).toBe("");
  });

  it("shows no position counter", () => {
    // "1 / 3" was a readout of a position the scroll itself now shows, sitting in the
    // corner the title has to clear.
    const { container } = renderWithContainer();
    expect(container.textContent).not.toMatch(/\d\s*\/\s*\d/);
  });

  it("keeps off-screen slides out of the tab order", () => {
    // Dropping `inert` was tried, on the grounds that a scrollable slide is reachable.
    // It puts every off-screen slide's Begin Scene button in the tab order, so a
    // keyboard user tabs through scenarios they cannot see. `index` follows the scroll,
    // so a slide stops being inert as it arrives.
    const second: ResolvedScenario = { ...scenario, id: "sc2", title: "The Second Hunt" };
    const { container } = render(
      <ScenarioCarousel
        slides={[scenario, second]}
        index={0}
        onPrev={vi.fn()}
        onNext={vi.fn()}
        onSelect={vi.fn()}
        onBegin={vi.fn()}
      />,
    );
    const slides = [...container.querySelectorAll(".snap-center")];
    expect(slides).toHaveLength(2);
    expect(slides[0].hasAttribute("inert")).toBe(false);
    expect(slides[1].hasAttribute("inert")).toBe(true);
    expect(slides[1].getAttribute("aria-hidden")).toBe("true");
  });

  /**
   * The scroll<->index guard, exercised directly.
   *
   * jsdom reports `clientWidth: 0` and never lays out, so the track's own numbers have to
   * be forced. That makes these tests about the LOGIC — which is the part that cannot be
   * checked by looking at it, and the part where a mistake is a jittering hero rather than
   * a wrong pixel.
   */
  function trackWith(slides: ResolvedScenario[], index: number, onSelect = vi.fn()) {
    const { container, rerender } = render(
      <ScenarioCarousel
        slides={slides}
        index={index}
        onPrev={vi.fn()}
        onNext={vi.fn()}
        onSelect={onSelect}
      />,
    );
    const track = container.querySelector<HTMLElement>(".scroll-track")!;
    Object.defineProperty(track, "clientWidth", { configurable: true, value: 300 });
    Object.defineProperty(track, "scrollLeft", { configurable: true, writable: true, value: index * 300 });
    // A smooth scroll fires `scroll` MANY times on its way, at positions that are not
    // the destination. Jumping straight there is the mistake that makes this fake useless:
    // the guard's whole job is the frames in between, and a fake without them passes
    // whether the guard is present or not (verified by deleting it).
    track.scrollTo = vi.fn(({ left = 0 }: ScrollToOptions = {}) => {
      const from = track.scrollLeft;
      for (const t of [0.2, 0.6, 1]) {
        Object.defineProperty(track, "scrollLeft", {
          configurable: true,
          writable: true,
          value: from + (left - from) * t,
        });
        fireEvent.scroll(track);
      }
    }) as typeof track.scrollTo;
    return { track, onSelect, rerender };
  }

  const two: ResolvedScenario[] = [scenario, { ...scenario, id: "sc2", title: "The Second Hunt" }];

  it("reports the slide a finger settles on", () => {
    const { track, onSelect } = trackWith(two, 0);
    Object.defineProperty(track, "scrollLeft", { configurable: true, writable: true, value: 300 });
    fireEvent.scroll(track);
    expect(onSelect).toHaveBeenCalledWith("sc2");
  });

  it("does not report the slide it was just told to show", () => {
    // The jitter this prevents: index changes -> effect scrolls -> the scroll fires ->
    // onSelect reports the same index -> the effect runs again. One of the two writers
    // has to stand down, and it is the one that did not initiate.
    const { track, onSelect, rerender } = trackWith(two, 0);
    onSelect.mockClear();
    rerender(
      <ScenarioCarousel
        slides={two}
        index={1}
        onPrev={vi.fn()}
        onNext={vi.fn()}
        onSelect={onSelect}
      />,
    );
    expect(track.scrollTo).toHaveBeenCalled();
    expect(onSelect).not.toHaveBeenCalled();

    // ...and the guard clears, so the NEXT finger movement is heard again.
    Object.defineProperty(track, "scrollLeft", { configurable: true, writable: true, value: 0 });
    fireEvent.scroll(track);
    expect(onSelect).toHaveBeenCalledWith("sc1");
  });

  it("does not scroll when the track is already where it was asked to be", () => {
    const { track, rerender } = trackWith(two, 1);
    (track.scrollTo as ReturnType<typeof vi.fn>).mockClear();
    rerender(
      <ScenarioCarousel
        slides={two}
        index={1}
        onPrev={vi.fn()}
        onNext={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    expect(track.scrollTo).not.toHaveBeenCalled();
  });

  it("hides the cast strip below lg", () => {
    // Two horizontally-scrolling strips nested inside each other is two swipe gestures
    // competing for one finger, and the cast is already on the Characters tab.
    const { container } = renderWithContainer();
    const strip = [...container.querySelectorAll<HTMLElement>(".overflow-x-auto")].find(
      (el) => !el.classList.contains("scroll-track"),
    )!;
    expect(strip.closest(".hidden")?.className).toContain("lg:flex");
  });
});

describe("ScenarioCarousel", () => {
  it("renders the empty state when there are no slides", () => {
    render(
      <ScenarioCarousel
        slides={[]}
        index={0}
        onPrev={vi.fn()}
        onNext={vi.fn()}
        onSelect={vi.fn()}
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
    const region = screen.getByRole("region", { name: /hunter krow statistics/i });
    expect(region).toBeInTheDocument();
    expect(screen.getByText(/no statistics available/i)).toBeInTheDocument();
    // The panel is an extension *inside* the same card (a grid column), not a
    // separate sibling box: it shares the card that holds the Hide-stats arrow.
    const card = region.closest(".group");
    expect(card).not.toBeNull();
    expect(
      within(card as HTMLElement).getByRole("button", { name: /hide statistics for hunter krow/i }),
    ).toBeInTheDocument();
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

  it("shows a character's real persisted stat value over the schema default", async () => {
    const user = userEvent.setup();
    renderCarousel({
      statDefs: [
        { key: "resolve", displayName: "Resolve", description: "", min: 0, max: 10, default: 7, visibility: "public", guidance: null, appliesTo: [], bands: [] },
      ],
      statsByCharId: { c1: { resolve: 3 } },
    });
    await user.click(screen.getByRole("button", { name: /show statistics for hunter krow/i }));
    const krowRegion = screen.getByRole("region", { name: /hunter krow statistics/i });
    expect(within(krowRegion).getByText("3")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /show statistics for ren/i }));
    // Ren has no persisted value for this stat — falls back to the schema default.
    const renRegion = screen.getByRole("region", { name: /ren statistics/i });
    expect(within(renRegion).getByText("7")).toBeInTheDocument();
  });

  it("shows a stat whose appliesTo is a node-type tag, not a per-character id list", async () => {
    // Regression: `appliesTo` is a type tag (e.g. "character" vs "setting") — the
    // backend's real default. It must not be mistaken for a list of character ids
    // (which would falsely exclude every real-world stat def from this panel).
    const user = userEvent.setup();
    renderCarousel({
      statDefs: [
        { key: "health", displayName: "Health", description: "", min: 0, max: 100, default: 100, visibility: "public", guidance: null, appliesTo: ["character"], bands: [] },
      ],
    });
    await user.click(screen.getByRole("button", { name: /show statistics for hunter krow/i }));
    const region = screen.getByRole("region", { name: /hunter krow statistics/i });
    expect(within(region).getByText("Health")).toBeInTheDocument();
    expect(within(region).getByText("100")).toBeInTheDocument();
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
    expect(container.querySelectorAll(".group.rounded-sm").length).toBe(2);
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
    // NOT just `.overflow-x-auto`: the hero itself is a scroll-snap track now, and it
    // matches that selector first. `.scroll-track` is the hero; the cast strip is the
    // other one.
    const strip = [...container.querySelectorAll<HTMLElement>(".overflow-x-auto")].find(
      (el) => !el.classList.contains("scroll-track"),
    )!;
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
      onBegin={vi.fn()}
      onProfile={vi.fn()}
    />,
  );
}
