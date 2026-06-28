"use client";

import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { mediaUrl } from "@/lib/api";
import { Monogram } from "@/components/ui/Monogram";
import type { Character, ResolvedScenario } from "@/lib/types";

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
        className="flex h-full transition-transform duration-[550ms] ease-[cubic-bezier(.45,.05,.2,1)]"
        style={{ transform: `translateX(-${index * 100}%)` }}
      >
        {slides.map((s, i) => (
          <div
            key={s.id}
            aria-hidden={i !== index}
            inert={i !== index}
            className="flex h-full flex-[0_0_100%]"
            style={{ background: HERO.panel, border: `1px solid ${HERO.border}` }}
          >
            {/* LEFT PANEL — scene art as background (sized to the 16:9 image
                aspect ratio), dark overlay, text + Begin Scene. */}
            <div
              className="relative flex aspect-[16/9] h-full flex-none flex-col overflow-hidden border-r"
              style={{ borderColor: HERO.divider }}
            >
              {/* Background: scene art image or hatched placeholder */}
              {s.image ? (
                // eslint-disable-next-line @next/next/no-img-element -- generated scene art from our media mount
                <img
                  src={mediaUrl(s.image)}
                  alt=""
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-0 h-full w-full object-cover"
                />
              ) : (
                <div
                  className="pointer-events-none absolute inset-0"
                  style={{ background: HERO.art }}
                />
              )}
              {/* Graduated scrim — strong on the left (under the title/description
                  column) and along the bottom (under the Begin button), fading to
                  near-clear on the right so the scene art reads boldly. Keeps the
                  left text column at AA while letting the artwork show through. */}
              <div
                className="pointer-events-none absolute inset-0"
                style={{
                  background:
                    "linear-gradient(96deg, rgba(18,12,5,0.9) 0%, rgba(18,12,5,0.74) 38%, rgba(18,12,5,0.34) 70%, rgba(18,12,5,0.12) 100%), linear-gradient(0deg, rgba(14,9,4,0.55) 0%, rgba(14,9,4,0) 42%)",
                }}
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
                    className="mt-[10px] w-full rounded-[2px] px-[4px] py-[8px] font-mono text-label uppercase tracking-[0.09em] hover:brightness-110"
                    style={{ background: HERO.label, color: "#1f160c" }}
                  >
                    Begin Scene ▸
                  </button>
                ) : null}
              </div>
            </div>

            {/* CHARACTER STRIP — an arrow-paged carousel of portrait cards */}
            <CastStrip cast={s.cast} onProfile={onProfile} />
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
  onProfile,
}: {
  cast: Character[];
  onProfile?: (id: string) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [nav, setNav] = useState({ overflow: false, atStart: true, atEnd: false });

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
  }, [measure, cast.length]);

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
            <CastCard key={c.id} c={c} onProfile={onProfile} />
          ))}
        </div>
      </div>

      {nav.overflow && !nav.atStart ? (
        <button
          type="button"
          onClick={() => page(-1)}
          aria-label="Previous characters"
          className="absolute left-[8px] top-1/2 z-[4] flex h-[30px] w-[30px] -translate-y-1/2 items-center justify-center rounded-full text-[16px] leading-none shadow-[0_2px_10px_rgba(8,5,2,0.55)] hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
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
          className="absolute right-[8px] top-1/2 z-[4] flex h-[30px] w-[30px] -translate-y-1/2 items-center justify-center rounded-full text-[16px] leading-none shadow-[0_2px_10px_rgba(8,5,2,0.55)] hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
          style={{ background: HERO.chev, border: `1px solid ${HERO.chevBd}`, color: HERO.label, outlineColor: HERO.label }}
        >
          ›
        </button>
      ) : null}
    </div>
  );
}

/** One full-bleed portrait card in the cast strip. */
function CastCard({ c, onProfile }: { c: Character; onProfile?: (id: string) => void }) {
  return (
    <div
      className="group relative flex w-[230px] flex-none flex-col overflow-hidden rounded-[8px] sm:w-[256px]"
      // Per-character framing: a colored hairline border + a soft outer glow
      // keyed to the character's accent (plus a neutral drop shadow for depth)
      // so each card reads as its own tile.
      style={{
        border: `1px solid ${c.color}8c`,
        boxShadow: `0 0 0 1px ${c.color}40, 0 0 14px 1px ${c.color}5e, 0 8px 20px rgba(8,5,2,0.5)`,
      }}
    >
      {/* Full-bleed portrait — or a tinted monogram fallback when no generated
          portrait exists yet. Decorative; the real name is in the footer below. */}
      {c.portrait ? (
        // eslint-disable-next-line @next/next/no-img-element -- generated portrait from our media mount
        <img
          src={mediaUrl(c.portrait)}
          alt=""
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 h-full w-full object-cover object-top"
        />
      ) : (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 flex items-start justify-center pt-[34px]"
          style={{ background: `linear-gradient(180deg, ${c.color}33, var(--field-bg))` }}
        >
          <span
            className="font-display font-bold leading-none"
            style={{ color: c.color, fontSize: 78, opacity: 0.42 }}
          >
            {c.mono}
          </span>
        </div>
      )}

      {/* Bottom scrim — a gentle fade that blends the portrait into the
          now-opaque footer plate below; the heavy near-opaque band is no longer
          needed since the footer is solid. */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "linear-gradient(180deg, rgba(20,14,6,0) 40%, rgba(14,9,4,0.34) 78%, rgba(12,8,3,0.55) 100%)",
        }}
      />

      {/* Corner wax-seal badge — the character's monogram + color ring */}
      <div className="pointer-events-none absolute right-[10px] top-[10px] z-[2]">
        <Monogram mono={c.mono} color={c.color} size={26} ring={2} />
      </div>

      {/* Footer — a SOLID accent-tinted plate (not see-through) so name / role /
          Statistics read independent of the portrait behind them; a thin accent
          top hairline frames it. */}
      <div
        className="relative z-[1] mt-auto flex flex-col p-[13px_14px_14px] sm:p-[14px_16px_15px]"
        style={{
          background: `color-mix(in srgb, ${c.color} 16%, #0e0a04)`,
          borderTop: `1px solid ${c.color}66`,
        }}
      >
        <div
          className="truncate font-display text-[16px] font-semibold leading-[1.15] sm:text-[18px]"
          // color-mix lightens the character's accent toward parchment so every
          // palette color clears AA over the dark footer plate while still
          // reading as that character's color.
          style={{ color: `color-mix(in srgb, ${c.color}, #F6ECDA)` }}
        >
          {c.name}
        </div>

        {c.role ? (
          <div className="mt-[2px] truncate font-mono text-label" style={{ color: LIGHT.loc }}>
            {c.role}
          </div>
        ) : null}

        {/* Statistics — its own non-transparent inset panel, tinted with the
            character's accent, so the block has a solid colored background
            instead of showing the portrait. Stat values aren't wired to the
            resolved Character yet → empty state. */}
        <div
          className="mt-[10px] rounded-[5px] px-[10px] py-[8px]"
          style={{
            background: `color-mix(in srgb, ${c.color} 22%, #0a0703)`,
            borderTop: `1px solid ${c.color}59`,
          }}
        >
          <div
            className="font-mono text-eyebrow uppercase tracking-[0.14em]"
            style={{ color: HERO.label }}
          >
            Statistics
          </div>
          <p className="mt-[3px] font-body text-body-sm italic" style={{ color: LIGHT.desc }}>
            No statistics available.
          </p>
        </div>
      </div>

      {/* Whole-card click target opens the character profile */}
      {onProfile ? (
        <button
          type="button"
          onClick={() => onProfile(c.id)}
          aria-label={`View ${c.name}`}
          title={c.name}
          className="absolute inset-0 z-[3] cursor-pointer transition-transform duration-200 ease-out group-hover:scale-[1.015] focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2"
          style={{ outlineColor: HERO.label }}
        />
      ) : null}
    </div>
  );
}
