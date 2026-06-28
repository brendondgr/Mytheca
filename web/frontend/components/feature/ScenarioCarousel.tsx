import { mediaUrl } from "@/lib/api";
import { Monogram } from "@/components/ui/Monogram";
import type { ResolvedScenario } from "@/lib/types";

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

            {/* CHARACTER STRIP — wide horizontal scroll of vertical character columns */}
            <div
              className="flex min-w-0 flex-1 overflow-x-auto overflow-y-hidden"
              style={{ scrollbarWidth: "thin", scrollbarColor: `${HERO.label}44 transparent` }}
            >
              <div className="flex h-full items-stretch">
                {s.cast.map((c) => (
                  <div
                    key={c.id}
                    className="group relative flex w-[250px] flex-none flex-col overflow-hidden border-r sm:w-[282px]"
                    style={{ borderColor: HERO.divider }}
                  >
                    {/* Full-bleed portrait — or a tinted monogram fallback when
                        no generated portrait exists yet. Decorative; the real
                        name is rendered in the footer below. */}
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

                    {/* Bottom scrim — the portrait reads clearly in the upper
                        ~55%, then the lower band darkens to near-opaque by the
                        footer line so the colored name + role + stats clear AA
                        over any artwork (even bright portraits). */}
                    <div
                      className="pointer-events-none absolute inset-0"
                      style={{
                        background:
                          "linear-gradient(180deg, rgba(20,14,6,0) 22%, rgba(18,12,5,0.5) 44%, rgba(14,9,4,0.9) 62%, rgba(10,6,2,0.97) 100%)",
                      }}
                    />

                    {/* Corner wax-seal badge — the character's monogram + color ring */}
                    <div className="pointer-events-none absolute right-[10px] top-[10px] z-[2]">
                      <Monogram mono={c.mono} color={c.color} size={26} ring={2} />
                    </div>

                    {/* Footer — name / role / divider / statistics, pinned to bottom */}
                    <div className="relative z-[1] mt-auto flex flex-col p-[14px_16px_15px] sm:p-[16px_20px_17px]">
                      <div
                        className="truncate font-display text-[16px] font-semibold leading-[1.15] sm:text-[18px]"
                        // color-mix lightens the character's accent toward parchment so
                        // every palette color clears AA over the dark scrim while still
                        // reading as that character's color.
                        style={{ color: `color-mix(in srgb, ${c.color}, #F6ECDA)` }}
                      >
                        {c.name}
                      </div>

                      {c.role ? (
                        <div
                          className="mt-[2px] truncate font-mono text-label"
                          style={{ color: LIGHT.loc }}
                        >
                          {c.role}
                        </div>
                      ) : null}

                      <div
                        className="mt-[10px] w-full border-t"
                        style={{ borderColor: "rgba(246,236,218,0.2)" }}
                      />

                      {/* Statistics — per-character stat values aren't wired to the
                          resolved Character yet, so this shows the empty state. */}
                      <div
                        className="mt-[8px] font-mono text-eyebrow uppercase tracking-[0.14em]"
                        style={{ color: HERO.label }}
                      >
                        Statistics
                      </div>
                      <p
                        className="mt-[3px] font-body text-body-sm italic"
                        style={{ color: LIGHT.desc }}
                      >
                        No statistics available.
                      </p>
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
                ))}
                {/* Trailing spacer */}
                <div className="w-[10px] flex-none" />
              </div>
            </div>
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
