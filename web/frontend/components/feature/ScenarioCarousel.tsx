"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { mediaUrl } from "@/lib/api";
import { Monogram } from "@/components/ui/Monogram";
import { SmartImage } from "@/components/ui/SmartImage";
import { Icon } from "@/components/ui/Icon";
import { CARD_SCRIM, PORTRAIT_SCRIM, OVER_ART } from "@/lib/cardArt";
import type { Character, ResolvedScenario, StatDefinition } from "@/lib/types";

// Theme-aware hero palette — all values reference CSS design tokens so the
// carousel adapts to Parchment / Ember / Slate automatically.
const HERO = {
  panel: "linear-gradient(135deg,var(--card-bg) 0%,var(--card-bg2) 60%,var(--card-bd) 100%)",
  art: "repeating-linear-gradient(45deg,var(--field-bg),var(--field-bg) 8px,var(--card-bg) 8px,var(--card-bg) 16px)",
  label: "#C8862A",       // gold — theme-agnostic per design-system.md
  medBg: "var(--field-bg)",
  toneText: "var(--ink-soft)",
  chev: "var(--field-bg)",
  chevBd: "var(--card-bd)",
  border: "var(--hair-strong)",
  divider: "var(--hair)",
};

// Light text constants for content rendered over the dark scene-art overlay.
const LIGHT = {
  title: "#F6ECDA",
  loc: "#E8D8B8",
  desc: "rgba(246,236,218,0.82)",
  toneBd: "rgba(200,134,42,0.4)",
  tone: "rgba(246,236,218,0.75)",
};

/** The recent-scenario hero carousel (display + prev/next navigation). */
export function ScenarioCarousel({
  slides,
  statDefs = [],
  statsByCharId = {},
  index,
  onPrev,
  onNext,
  onSelect,
  onBegin,
  onProfile,
  // Edit button removed from carousel — prop kept for caller compat.
  onEdit: _onEdit,
}: {
  slides: ResolvedScenario[];
  /** Active storyline's stat definitions — shown in each cast card's stats panel. */
  statDefs?: StatDefinition[];
  /** Each cast member's persisted stat values, keyed by character id — real values
   * shown over the schema default when known. */
  statsByCharId?: Record<string, Record<string, number>>;
  index: number;
  onPrev: () => void;
  onNext: () => void;
  onSelect: (id: string) => void;
  onBegin?: (id: string) => void;
  onProfile?: (id: string) => void;
  onEdit?: (id: string) => void;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  /**
   * Which slide the SCROLL currently shows, guarded so the two directions cannot fight.
   *
   * Two things move this track: a finger, and `index` changing from outside (the chevrons,
   * or selecting a card in the Scenarios column below). Without the guard they feed each
   * other — a programmatic scroll fires `scroll`, which reports an index, which re-runs the
   * effect, which scrolls again — and the track jitters instead of settling.
   */
  const settlingTo = useRef<number | null>(null);

  const onTrackScroll = useCallback(() => {
    const el = trackRef.current;
    if (!el || el.clientWidth === 0) return;
    const at = Math.round(el.scrollLeft / el.clientWidth);
    if (settlingTo.current !== null) {
      // Ignore everything until the programmatic scroll has arrived where it was sent.
      if (at === settlingTo.current) settlingTo.current = null;
      return;
    }
    const slide = slides[at];
    if (slide && at !== index) onSelect(slide.id);
  }, [index, onSelect, slides]);

  // `index` moved without the finger — scroll the track to match.
  useEffect(() => {
    const el = trackRef.current;
    if (!el || el.clientWidth === 0) return;
    const want = index * el.clientWidth;
    if (Math.abs(el.scrollLeft - want) < 2) return;
    settlingTo.current = index;
    // `auto` under reduced motion: `scroll-behavior: smooth` on a 100%-wide track is a
    // full-screen slide, which is exactly the movement that rule exists to suppress.
    el.scrollTo({
      left: want,
      behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  }, [index]);

  if (slides.length === 0) {
    return (
      <section
        aria-label="Recent scenarios"
        className="relative mx-lg mt-lg flex h-[326px] flex-none flex-col items-center justify-center gap-sm overflow-hidden rounded-sm shadow-[0_6px_22px_rgba(20,14,6,.18)] sm:mx-xl"
        style={{ background: HERO.panel, border: `1px solid ${HERO.border}` }}
      >
        <span
          className="font-mono text-tag uppercase tracking-[0.22em]"
          style={{ color: HERO.label }}
        >
          No scenarios yet
        </span>
        <p
          className="max-w-[420px] px-4 text-center font-body text-body-sm italic"
          style={{ color: HERO.toneText }}
        >
          This storyline has no scenes. Use{" "}
          <span style={{ color: HERO.label }}>+ Create</span> to assemble its
          first scenario.
        </p>
      </section>
    );
  }

  return (
    <section
      aria-roledescription="carousel"
      aria-label="Recent scenarios"
      className="relative mx-lg mt-lg h-[326px] flex-none overflow-hidden rounded-sm shadow-[0_6px_22px_rgba(20,14,6,.18)] sm:mx-xl"
    >
      {/* A native scroll-snap track, not a transform pager.
       *
       * Swipe and click-drag come free, and so do the trackpad, the arrow keys and a
       * screen reader's own scrolling — none of which a `translateX` on a parent has
       * any answer for. The chevrons still work: they move `index`, and the effect
       * below scrolls the track to match, which is also what makes an external change
       * (clicking a card in the Scenarios column) move the hero. */}
      <div
        ref={trackRef}
        onScroll={onTrackScroll}
        className="scroll-track flex h-full w-full snap-x snap-mandatory overflow-x-auto overflow-y-hidden"
      >
        {slides.map((s, i) => (
          <div
            key={s.id}
            // Still `inert`, and it still tracks the visible slide — `index` now follows
            // the SCROLL, so a slide stops being inert as it arrives. Dropping it because
            // "the user can scroll there" was tried and is wrong: it puts every off-screen
            // slide's Begin Scene button in the tab order, so a keyboard user tabs through
            // three scenarios they cannot see. Scrolling is unaffected — a touch on an
            // inert child still finds the scrollable ancestor.
            aria-hidden={i !== index}
            inert={i !== index}
            className="flex h-full w-full min-w-0 flex-[0_0_100%] snap-center"
            style={{ background: HERO.panel, border: `1px solid ${HERO.border}` }}
          >
            {/* LEFT PANEL — scene art as background (sized to the 16:9 image
                aspect ratio), dark overlay, text + Begin Scene. */}
            {/* Full width below `lg`, where the cast strip beside it is hidden. A 16:9
                panel with nothing to its right leaves a third of a phone's hero blank. */}
            <div
              className="relative flex h-full w-full min-w-0 flex-1 flex-col overflow-hidden border-r lg:aspect-[16/9] lg:w-auto lg:flex-none"
              style={{ borderColor: HERO.divider }}
            >
              {/* Background: scene art image or hatched placeholder. The hero
                  panel is the carousel's LCP image, so it loads eagerly. */}
              <SmartImage
                src={s.image ? mediaUrl(s.image) : null}
                alt=""
                fill
                priority
                className="pointer-events-none"
                placeholder={<div className="h-full w-full" style={{ background: HERO.art }} />}
              />
              {/* Graduated scrim — strong on the left (under the title/description
                  column) and along the bottom (under the Begin button), fading to
                  near-clear on the right so the scene art reads boldly. Keeps the
                  left text column at AA while letting the artwork show through. */}
              <div
                aria-hidden
                className="pointer-events-none absolute inset-0"
                style={{ background: CARD_SCRIM }}
              />

              {/* Text content above the overlay — capped width for readable
                  line length even on the wide 16:9 panel. */}
              {/* The top reserve clears the absolutely-positioned overlay row above.
                  42px did not: the title's first line began 20px inside that band and ran
                  under the pager at 390px. Nothing overflowed the viewport, so every
                  responsive check was silent — an overlap is invisible to a `scrollWidth`
                  gate and the first thing a person sees. 48 + 16 = 64px, from scale steps
                  rather than a measured literal. Below `sm` the row is only the label, so
                  the reserve is generous there rather than exact; it is a floor. */}
              {/* `justify-center`: the block sits in the middle of the panel rather than
                  pinned under the label, which is what the top reserve used to be for.
                  The reserve stays — the "Recent Scenario" label still overlays the top —
                  but it is now a floor rather than the whole layout. */}
              <div className="relative z-[1] flex w-full max-w-[340px] flex-1 flex-col justify-center overflow-hidden px-lg pt-[calc(var(--sp-3xl)+var(--sp-lg))] pb-lg sm:px-xl">
                <h2
                  className="font-display text-step-2 font-bold leading-[1.08] sm:text-step-2"
                  style={{ color: LIGHT.title }}
                >
                  {s.title}
                </h2>

                {/* Location */}
                <div className="mt-xs flex items-baseline gap-2xs">
                  <span
                    className="flex-none font-mono text-eyebrow uppercase tracking-[0.18em]"
                    style={{ color: HERO.label }}
                  >
                    Location
                  </span>
                  <span
                    className="font-mono text-label font-medium"
                    style={{ color: LIGHT.loc }}
                  >
                    ◆ {s.setting.name}
                  </span>
                </div>

                {/* Genre / tone tags */}
                <div className="mt-sm flex flex-wrap gap-2xs">
                  <span
                    className="rounded-xs px-xs py-3xs font-mono text-tag uppercase tracking-[0.09em]"
                    style={{ background: HERO.label, color: "#1f160c" }}
                  >
                    {s.genre}
                  </span>
                  <span
                    className="rounded-xs border px-xs py-3xs font-mono text-tag uppercase tracking-[0.09em]"
                    style={{ color: LIGHT.tone, borderColor: LIGHT.toneBd }}
                  >
                    {s.tone}
                  </span>
                </div>

                {/* Description — grows to fill remaining space */}
                <p
                  className="mt-sm flex-1 overflow-hidden font-body text-body-sm leading-[1.42] line-clamp-6"
                  style={{ color: LIGHT.desc }}
                >
                  {s.goal}
                </p>

                {/* Begin Scene — pinned at bottom */}
                {onBegin ? (
                  <button
                    type="button"
                    onClick={() => onBegin(s.id)}
                    className="mt-sm w-full rounded-xs px-2xs py-sm font-mono text-label uppercase tracking-[0.09em] hover-lift press hover:brightness-[1.18] hover:shadow-[0_5px_14px_rgba(10,6,3,.35)] active:translate-y-0"
                    style={{ background: HERO.label, color: "#1f160c" }}
                  >
                    Begin Scene ▸
                  </button>
                ) : null}
              </div>
            </div>

            {/* CHARACTER STRIP — an arrow-paged carousel of portrait cards.
                `lg`-only: the cast is already on the Characters tab and on the scenario
                card below, and a second horizontally-scrolling strip inside a
                horizontally-scrolling hero is two swipe gestures competing for one
                finger. */}
            <div className="hidden min-w-0 flex-1 lg:flex">
              <CastStrip cast={s.cast} statDefs={statDefs} statsByCharId={statsByCharId} onProfile={onProfile} />
            </div>
          </div>
        ))}
      </div>

      {/* overlay: "Recent Scenario" label + chevrons + counter */}
      <div className="pointer-events-none absolute top-lg left-[16px] right-[16px] flex items-center gap-3 sm:left-[30px]">
        <span
          className="font-mono text-tag uppercase tracking-[0.22em]"
          style={{ color: HERO.label }}
        >
          Recent Scenario
        </span>
        {/* Chevrons at `sm` and above only, and no counter at any width.
         *
         * On a phone the track is swipeable, so the chevrons are a second way to do what
         * a finger already does — and the "1 / 3" beside them was a readout of a position
         * the scroll itself shows. Both were in the corner the title has to clear, which
         * is what the 64px top reserve below is paying for. */}
        <div className="pointer-events-auto hidden items-center gap-xs sm:flex">
          <button
            type="button"
            onClick={onPrev}
            aria-label="Previous scenario"
            className="flex h-[22px] w-[22px] items-center justify-center rounded-full leading-none"
            style={{ background: HERO.chev, border: `1px solid ${HERO.chevBd}`, color: HERO.label }}
          >
            <Icon name="back" size={11} strokeWidth={2.4} />
          </button>
          <button
            type="button"
            onClick={onNext}
            aria-label="Next scenario"
            className="flex h-[22px] w-[22px] items-center justify-center rounded-full leading-none"
            style={{ background: HERO.chev, border: `1px solid ${HERO.chevBd}`, color: HERO.label }}
          >
            <Icon name="forward" size={11} strokeWidth={2.4} />
          </button>
        </div>
      </div>
    </section>
  );
}

/**
 * The horizontally-scrolling cast strip for one scenario slide. Native scroll is
 * preserved (keyboard / trackpad); when the cards overflow the visible width it
 * additionally shows left/right arrow buttons that page the strip — and each
 * arrow hides at its respective end so they only appear when there's somewhere
 * to go. Overflow is measured from the DOM (mount + scroll + resize +
 * ResizeObserver when available); under jsdom (no layout) the arrows stay hidden.
 */
function CastStrip({
  cast,
  statDefs,
  statsByCharId,
  onProfile,
}: {
  cast: Character[];
  statDefs: StatDefinition[];
  statsByCharId: Record<string, Record<string, number>>;
  onProfile?: (id: string) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [nav, setNav] = useState({ overflow: false, atStart: true, atEnd: false });
  // Which card's inline statistics panel is open (one at a time). The panel is a
  // flex sibling inserted after that card, so it pushes the following cards over.
  const [openStatsId, setOpenStatsId] = useState<string | null>(null);

  const measure = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    setNav({
      overflow: max > 1,
      atStart: el.scrollLeft <= 1,
      atEnd: el.scrollLeft >= max - 1,
    });
  }, []);

  useLayoutEffect(() => {
    measure();
    const el = scrollRef.current;
    if (!el) return;
    let ro: ResizeObserver | undefined;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(measure);
      ro.observe(el);
    }
    window.addEventListener("resize", measure);
    return () => {
      ro?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [measure, cast.length, openStatsId]);

  // The stats extension slides open over ~300ms, growing the scroll content after
  // the synchronous measure above — re-measure once it settles so the overflow
  // arrows reflect the final width.
  useEffect(() => {
    const t = setTimeout(measure, 340);
    return () => clearTimeout(t);
  }, [measure, openStatsId]);

  const page = useCallback((dir: number) => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollBy({ left: dir * el.clientWidth * 0.85, behavior: "smooth" });
  }, []);

  return (
    <div className="relative flex min-w-0 flex-1">
      <div
        ref={scrollRef}
        onScroll={measure}
        className="flex min-w-0 flex-1 overflow-x-auto overflow-y-hidden"
        style={{ scrollbarWidth: "thin", scrollbarColor: `${HERO.label}44 transparent` }}
      >
        <div className="flex h-full items-stretch gap-lg p-lg">
          {cast.map((c) => (
            <CastCard
              key={c.id}
              c={c}
              statDefs={statDefs}
              statValues={statsByCharId[c.id]}
              expanded={openStatsId === c.id}
              onToggleStats={() =>
                setOpenStatsId((id) => (id === c.id ? null : c.id))
              }
              onProfile={onProfile}
            />
          ))}
        </div>
      </div>

      {nav.overflow && !nav.atStart ? (
        <button
          type="button"
          onClick={() => page(-1)}
          aria-label="Previous characters"
          className="absolute left-[8px] top-1/2 z-[4] flex h-[30px] w-[30px] -translate-y-1/2 items-center justify-center rounded-full text-body leading-none shadow-[0_2px_10px_rgba(8,5,2,0.55)] hover:brightness-125 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
          style={{ background: HERO.chev, border: `1px solid ${HERO.chevBd}`, color: HERO.label, outlineColor: HERO.label }}
        >
          ‹
        </button>
      ) : null}
      {nav.overflow && !nav.atEnd ? (
        <button
          type="button"
          onClick={() => page(1)}
          aria-label="Next characters"
          className="absolute right-[8px] top-1/2 z-[4] flex h-[30px] w-[30px] -translate-y-1/2 items-center justify-center rounded-full text-body leading-none shadow-[0_2px_10px_rgba(8,5,2,0.55)] hover:brightness-125 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
          style={{ background: HERO.chev, border: `1px solid ${HERO.chevBd}`, color: HERO.label, outlineColor: HERO.label }}
        >
          ›
        </button>
      ) : null}
    </div>
  );
}

// Width (px) of the statistics extension that slides out of a cast card.
const CAST_STATS_W = 208;

/**
 * One cast tile in the strip — transparent like the Library `CharacterCard`: the
 * portrait fills a fixed-width column behind the shared `PORTRAIT_SCRIM` with
 * name/role over it (monogram fallback on a solid surface), framed in the
 * character's color. The `❯` arrow slides out an attached **statistics
 * extension** *inside the same bordered card* (width animates 0 → CAST_STATS_W),
 * so the stats read as the card growing rather than a separate box; the wider
 * card pushes the following cards over.
 */
function CastCard({
  c,
  statDefs,
  statValues,
  expanded,
  onToggleStats,
  onProfile,
}: {
  c: Character;
  statDefs: StatDefinition[];
  statValues?: Record<string, number>;
  expanded: boolean;
  onToggleStats: () => void;
  onProfile?: (id: string) => void;
}) {
  const hasPortrait = Boolean(c.portrait);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Reveal the grown card when its stats open. Optional-call: jsdom (tests)
    // doesn't implement scrollIntoView.
    if (expanded) {
      ref.current?.scrollIntoView?.({ behavior: "smooth", inline: "nearest", block: "nearest" });
    }
  }, [expanded]);

  return (
    <div
      ref={ref}
      className="group relative grid h-full flex-none overflow-hidden rounded-sm transition-[grid-template-columns] duration-base ease-out motion-reduce:transition-none"
      // The card is a 2-column grid: a fixed portrait column + a stats column that
      // animates 0px → CAST_STATS_W when opened. Animating `grid-template-columns`
      // slides the extension out as part of the same bordered card and pushes the
      // following cards over — reliable where a flex `width` transition is not.
      style={{
        border: `2px solid ${c.color}`,
        gridTemplateColumns: `200px ${expanded ? CAST_STATS_W : 0}px`,
      }}
    >
      {/* Portrait column — the image/scrim/footer/buttons live here. */}
      <div
        className="relative h-full overflow-hidden"
        style={{ background: hasPortrait ? undefined : "var(--card-bg2)" }}
      >
        <SmartImage
          src={hasPortrait ? mediaUrl(c.portrait!) : null}
          alt=""
          fill
          imgClassName="object-top"
          className="pointer-events-none"
          placeholder={
            <div className="flex h-full w-full items-center justify-center pb-3xl">
              <Monogram mono={c.mono} color={c.color} size={84} ring={2} fontSize={32} />
            </div>
          }
        />

        {/* Transparent bottom scrim — name/role read over the lower portrait. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{ background: PORTRAIT_SCRIM }}
        />

        {/* Footer over the scrim: name + role (light text, theme-independent). */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[1] p-[11px_12px_12px]">
          <div
            className="truncate font-display text-body-sm font-semibold leading-[1.12] sm:text-body"
            style={{ color: OVER_ART.title }}
            title={c.name}
          >
            {c.name}
          </div>
          {c.role ? (
            <div
              className="mt-3xs truncate font-mono text-label"
              style={{ color: OVER_ART.eyebrow }}
            >
              {c.role}
            </div>
          ) : null}
        </div>

        {/* Whole-portrait click target opens the character profile. */}
        {onProfile ? (
          <button
            type="button"
            onClick={() => onProfile(c.id)}
            aria-label={`View ${c.name}`}
            title={c.name}
            className="absolute inset-0 z-[3] cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2"
            style={{ outlineColor: HERO.label }}
          />
        ) : null}

        {/* Stats arrow (above the profile button) — slides the extension out/in. */}
        <button
          type="button"
          onClick={onToggleStats}
          aria-label={expanded ? `Hide statistics for ${c.name}` : `Show statistics for ${c.name}`}
          aria-expanded={expanded}
          className="absolute right-[8px] top-sm z-[5] flex h-[26px] w-[26px] items-center justify-center rounded-full text-label leading-none shadow-[0_2px_8px_rgba(8,5,2,0.5)] hover:brightness-125 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
          style={{ background: HERO.chev, border: `1px solid ${c.color}`, color: HERO.label, outlineColor: HERO.label }}
        >
          {expanded ? "❮" : "❯"}
        </button>
      </div>

      {/* Statistics extension — the second grid column; slides open on toggle as
          part of the same card (its track width animates above). */}
      <div
        aria-hidden={!expanded}
        className="h-full min-w-0 overflow-hidden"
        style={{
          borderLeft: expanded ? `1px solid ${c.color}59` : undefined,
          background: `color-mix(in srgb, ${c.color} 14%, #0e0a04)`,
        }}
      >
        {expanded ? (
          <CastStats
            c={c}
            statDefs={statDefs}
            statValues={statValues}
            width={CAST_STATS_W}
            onClose={onToggleStats}
          />
        ) : null}
      </div>
    </div>
  );
}

/**
 * The statistics content shown inside a cast card's slide-out extension. Lists
 * the storyline's player-visible (public) stat definitions that apply to this
 * character with their real persisted value (falling back to the schema default
 * for a stat never explicitly set); falls back to an empty-state line when there
 * are no public stats at all. Fixed width so it doesn't reflow while the
 * extension animates open.
 */
function CastStats({
  c,
  statDefs,
  statValues,
  width,
  onClose,
}: {
  c: Character;
  statDefs: StatDefinition[];
  statValues?: Record<string, number>;
  width: number;
  onClose: () => void;
}) {
  // `appliesTo` is a node-TYPE tag (e.g. "character" vs "setting"), not a list of
  // specific character ids — every other stat consumer (CharacterCard, CastRail,
  // DirectorRail, CharacterProfileModal) filters on visibility alone; matching that.
  const stats = statDefs.filter((d) => d.visibility === "public");
  return (
    <div
      role="region"
      aria-label={`${c.name} statistics`}
      className="flex h-full flex-col"
      style={{ width }}
    >
      <div className="flex items-start justify-between gap-2 px-md pt-md">
        <div className="min-w-0">
          <div
            className="font-mono text-eyebrow uppercase tracking-[0.16em]"
            style={{ color: HERO.label }}
          >
            Statistics
          </div>
          <div className="truncate font-display text-body-sm font-semibold" style={{ color: OVER_ART.title }}>
            {c.name}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close statistics"
          className="flex h-[20px] w-[20px] flex-none items-center justify-center rounded-full text-eyebrow leading-none hover:brightness-125 focus-visible:outline focus-visible:outline-2"
          style={{ color: OVER_ART.title, background: `${c.color}55`, outlineColor: HERO.label }}
        >
          ×
        </button>
      </div>
      <div className="mt-sm min-h-0 flex-1 overflow-y-auto px-md pb-md">
        {stats.length === 0 ? (
          <p className="font-body text-body-sm italic" style={{ color: LIGHT.desc }}>
            No statistics available.
          </p>
        ) : (
          <ul className="flex flex-col gap-xs">
            {stats.map((d) => (
              <li key={d.key} className="flex items-baseline justify-between gap-2">
                <span className="truncate font-body text-body-sm" style={{ color: LIGHT.loc }}>
                  {d.displayName}
                </span>
                <span className="flex-none font-mono text-label" style={{ color: OVER_ART.title }}>
                  {statValues?.[d.key] ?? d.default}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
