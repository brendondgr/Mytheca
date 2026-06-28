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
              {/* Dark overlay so text remains readable against any art */}
              <div
                className="pointer-events-none absolute inset-0"
                style={{ background: "rgba(20,14,6,0.68)" }}
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
                    className="flex w-[250px] flex-none flex-col items-center border-r px-[16px] pb-[14px] pt-[16px] sm:w-[282px] sm:px-[20px]"
                    style={{ borderColor: HERO.divider }}
                  >
                    {/* Portrait — high up in the card */}
                    {onProfile ? (
                      <button
                        type="button"
                        onClick={() => onProfile(c.id)}
                        aria-label={`View ${c.name}`}
                        title={c.name}
                        className="flex-none rounded-full transition-transform hover:scale-110"
                      >
                        <Monogram
                          mono={c.mono}
                          color={c.color}
                          size={56}
                          ring={2}
                          bg={HERO.medBg}
                          src={c.portrait ? mediaUrl(c.portrait) : undefined}
                        />
                      </button>
                    ) : (
                      <Monogram
                        mono={c.mono}
                        color={c.color}
                        size={56}
                        ring={2}
                        bg={HERO.medBg}
                        src={c.portrait ? mediaUrl(c.portrait) : undefined}
                      />
                    )}

                    {/* Character name */}
                    <div
                      className="mt-[7px] w-full truncate text-center font-display text-[14px] font-semibold leading-[1.2] sm:text-[16px]"
                      style={{ color: c.color }}
                    >
                      {c.name}
                    </div>

                    {/* Role — value only, no label */}
                    {c.role ? (
                      <div
                        className="mt-[2px] w-full truncate text-center font-mono text-label"
                        style={{ color: HERO.toneText }}
                      >
                        {c.role}
                      </div>
                    ) : null}

                    {/* Divider */}
                    <div
                      className="mt-[9px] w-full border-t"
                      style={{ borderColor: HERO.divider }}
                    />

                    {/* Statistics — per-character stat values are not wired to the
                        resolved Character yet, so this shows the empty state. */}
                    <div className="mt-[9px] w-full flex-1 overflow-y-auto pr-[2px]">
                      <div
                        className="font-mono text-eyebrow uppercase tracking-[0.14em]"
                        style={{ color: HERO.label }}
                      >
                        Statistics
                      </div>
                      <p
                        className="mt-[4px] font-body text-body-sm italic"
                        style={{ color: HERO.toneText }}
                      >
                        No statistics available.
                      </p>
                    </div>
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
