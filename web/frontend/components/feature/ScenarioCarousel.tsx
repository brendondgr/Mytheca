"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { mediaUrl } from "@/lib/api";
import { Monogram } from "@/components/ui/Monogram";
import { SmartImage } from "@/components/ui/SmartImage";
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
  counterText,
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
  counterText: string;
  onBegin?: (id: string) => void;
  onProfile?: (id: string) => void;
  onEdit?: (id: string) => void;
}) {
  if (slides.length === 0) {
    return (
      <section
        aria-label="Recent scenarios"
        className="relative mx-[16px] mt-[18px] flex h-[326px] flex-none flex-col items-center justify-center gap-[8px] overflow-hidden rounded-[5px] shadow-[0_6px_22px_rgba(20,14,6,.18)] sm:mx-[28px]"
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
      className="relative mx-[16px] mt-[18px] h-[326px] flex-none overflow-hidden rounded-[5px] shadow-[0_6px_22px_rgba(20,14,6,.18)] sm:mx-[28px]"
    >
      <div
        className="flex h-full w-full transition-transform duration-slow ease-out"
        style={{ transform: `translateX(-${index * 100}%)` }}
      >
        {slides.map((s, i) => (
          <div
            key={s.id}
            aria-hidden={i !== index}
            inert={i !== index}
            className="flex h-full w-full min-w-0 flex-[0_0_100%]"
            style={{ background: HERO.panel, border: `1px solid ${HERO.border}` }}
          >
            {/* LEFT PANEL — scene art as background (sized to the 16:9 image
                aspect ratio), dark overlay, text + Begin Scene. */}
            <div
              className="relative flex aspect-[16/9] h-full flex-none flex-col overflow-hidden border-r"
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
              <div className="relative z-[1] flex w-full max-w-[340px] flex-1 flex-col overflow-hidden p-[42px_16px_16px] sm:p-[46px_20px_18px]">
                <h2
                  className="font-display text-[21px] font-bold leading-[1.08] sm:text-[25px]"
                  style={{ color: LIGHT.title }}
                >
                  {s.title}
                </h2>

                {/* Location */}
                <div className="mt-[7px] flex items-baseline gap-[5px]">
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
                <div className="mt-[8px] flex flex-wrap gap-[5px]">
                  <span
                    className="rounded-[2px] px-[7px] py-[2px] font-mono text-tag uppercase tracking-[0.09em]"
                    style={{ background: HERO.label, color: "#1f160c" }}
                  >
                    {s.genre}
                  </span>
                  <span
                    className="rounded-[2px] border px-[7px] py-[2px] font-mono text-tag uppercase tracking-[0.09em]"
                    style={{ color: LIGHT.tone, borderColor: LIGHT.toneBd }}
                  >
                    {s.tone}
                  </span>
                </div>

                {/* Description — grows to fill remaining space */}
                <p
                  className="mt-[9px] flex-1 overflow-hidden font-body text-body-sm leading-[1.42] line-clamp-6"
                  style={{ color: LIGHT.desc }}
                >
                  {s.goal}
                </p>

                {/* Begin Scene — pinned at bottom */}
                {onBegin ? (
                  <button
                    type="button"
                    onClick={() => onBegin(s.id)}
                    className="mt-[10px] w-full rounded-[2px] px-[4px] py-[8px] font-mono text-label uppercase tracking-[0.09em] hover-lift press hover:brightness-[1.18] hover:shadow-[0_5px_14px_rgba(10,6,3,.35)] active:translate-y-0"
                    style={{ background: HERO.label, color: "#1f160c" }}
                  >
                    Begin Scene ▸
                  </button>
                ) : null}
              </div>
            </div>

            {/* CHARACTER STRIP — an arrow-paged carousel of portrait cards */}
            <CastStrip cast={s.cast} statDefs={statDefs} statsByCharId={statsByCharId} onProfile={onProfile} />
          </div>
        ))}
      </div>

      {/* overlay: "Recent Scenario" label + chevrons + counter */}
      <div className="pointer-events-none absolute top-[14px] left-[16px] right-[16px] flex items-center gap-3 sm:left-[30px]">
        <span
          className="font-mono text-tag uppercase tracking-[0.22em]"
          style={{ color: HERO.label }}
        >
          Recent Scenario
        </span>
        <div className="pointer-events-auto flex items-center gap-[6px]">
          <button
            type="button"
            onClick={onPrev}
            aria-label="Previous scenario"
            className="flex h-[22px] w-[22px] items-center justify-center rounded-full text-[13px] leading-none"
            style={{ background: HERO.chev, border: `1px solid ${HERO.chevBd}`, color: HERO.label }}
          >
            ‹
          </button>
          <span className="font-mono text-tag" style={{ color: HERO.label }}>
            {counterText}
          </span>
          <button
            type="button"
            onClick={onNext}
            aria-label="Next scenario"
            className="flex h-[22px] w-[22px] items-center justify-center rounded-full text-[13px] leading-none"
            style={{ background: HERO.chev, border: `1px solid ${HERO.chevBd}`, color: HERO.label }}
          >
            ›
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
        <div className="flex h-full items-stretch gap-[16px] p-[16px]">
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
          className="absolute left-[8px] top-1/2 z-[4] flex h-[30px] w-[30px] -translate-y-1/2 items-center justify-center rounded-full text-[16px] leading-none shadow-[0_2px_10px_rgba(8,5,2,0.55)] hover:brightness-125 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
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
          className="absolute right-[8px] top-1/2 z-[4] flex h-[30px] w-[30px] -translate-y-1/2 items-center justify-center rounded-full text-[16px] leading-none shadow-[0_2px_10px_rgba(8,5,2,0.55)] hover:brightness-125 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
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
      className="group relative grid h-full flex-none overflow-hidden rounded-[6px] transition-[grid-template-columns] duration-base ease-out motion-reduce:transition-none"
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
            <div className="flex h-full w-full items-center justify-center pb-[52px]">
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
            className="truncate font-display text-[15px] font-semibold leading-[1.12] sm:text-[16px]"
            style={{ color: OVER_ART.title }}
            title={c.name}
          >
            {c.name}
          </div>
          {c.role ? (
            <div
              className="mt-[2px] truncate font-mono text-label"
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
          className="absolute right-[8px] top-[8px] z-[5] flex h-[26px] w-[26px] items-center justify-center rounded-full text-[13px] leading-none shadow-[0_2px_8px_rgba(8,5,2,0.5)] hover:brightness-125 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
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
      <div className="flex items-start justify-between gap-2 px-[12px] pt-[12px]">
        <div className="min-w-0">
          <div
            className="font-mono text-eyebrow uppercase tracking-[0.16em]"
            style={{ color: HERO.label }}
          >
            Statistics
          </div>
          <div className="truncate font-display text-[14px] font-semibold" style={{ color: OVER_ART.title }}>
            {c.name}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close statistics"
          className="flex h-[20px] w-[20px] flex-none items-center justify-center rounded-full text-[12px] leading-none hover:brightness-125 focus-visible:outline focus-visible:outline-2"
          style={{ color: OVER_ART.title, background: `${c.color}55`, outlineColor: HERO.label }}
        >
          ×
        </button>
      </div>
      <div className="mt-[8px] min-h-0 flex-1 overflow-y-auto px-[12px] pb-[12px]">
        {stats.length === 0 ? (
          <p className="font-body text-body-sm italic" style={{ color: LIGHT.desc }}>
            No statistics available.
          </p>
        ) : (
          <ul className="flex flex-col gap-[6px]">
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
