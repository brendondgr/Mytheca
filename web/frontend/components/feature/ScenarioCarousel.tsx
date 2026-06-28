import { mediaUrl } from "@/lib/api";
import { Monogram } from "@/components/ui/Monogram";
import type { ResolvedScenario } from "@/lib/types";

// Theme-aware hero palette — all values reference CSS design tokens so the
// carousel adapts to Parchment / Ember / Slate automatically.
const HERO = {
  panel: "linear-gradient(135deg,var(--card-bg) 0%,var(--card-bg2) 60%,var(--card-bd) 100%)",
  art: "repeating-linear-gradient(45deg,var(--field-bg),var(--field-bg) 8px,var(--card-bg) 8px,var(--card-bg) 16px)",
  title: "var(--ink)",
  goal: "var(--ink-soft)",
  label: "#C8862A",       // gold — theme-agnostic per design-system.md
  medBg: "var(--field-bg)",
  artLabel: "var(--mute2)",
  artLabelBg: "var(--field-bg)",
  chev: "var(--field-bg)",
  chevBd: "var(--card-bd)",
  toneText: "var(--ink-soft)",
  border: "var(--hair-strong)",
  divider: "var(--hair)",
  statKey: "var(--mute)",
};

// Scene art panel: aspect-[16/9] × h-[246px] → width ≈ 437px.
// Used to keep the header overlay and dots within the narrative+cast zone at lg.
const ART_RIGHT = "437px";

/** The recent-scenario hero carousel (display + prev/next/dots navigation). */
export function ScenarioCarousel({
  slides,
  index,
  onPrev,
  onNext,
  onSelect,
  counterText,
  onBegin,
  onProfile,
  onEdit,
}: {
  slides: ResolvedScenario[];
  index: number;
  onPrev: () => void;
  onNext: () => void;
  onSelect: (id: string) => void;
  counterText: string;
  onBegin?: (id: string) => void;
  onProfile?: (id: string) => void;
  /** When provided, shows a ✎ edit button in the header row. */
  onEdit?: (id: string) => void;
}) {
  if (slides.length === 0) {
    return (
      <section
        aria-label="Recent scenarios"
        className="relative mx-[16px] mt-[18px] flex h-[246px] flex-none flex-col items-center justify-center gap-[8px] overflow-hidden rounded-[5px] shadow-[0_6px_22px_rgba(20,14,6,.18)] sm:mx-[28px]"
        style={{ background: HERO.panel, border: `1px solid ${HERO.border}` }}
      >
        <span
          className="font-mono text-tag uppercase tracking-[0.22em]"
          style={{ color: HERO.label }}
        >
          No scenarios yet
        </span>
        <p
          className="max-w-[420px] px-4 text-center font-body text-[15px] italic"
          style={{ color: HERO.goal }}
        >
          This storyline has no scenes. Use{" "}
          <span style={{ color: HERO.label }}>+ Create</span> to assemble its
          first scenario.
        </p>
      </section>
    );
  }

  const current = slides[index];

  return (
    <section
      aria-roledescription="carousel"
      aria-label="Recent scenarios"
      className="relative mx-[16px] mt-[18px] h-[246px] flex-none overflow-hidden rounded-[5px] shadow-[0_6px_22px_rgba(20,14,6,.18)] sm:mx-[28px]"
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
            {/* LEFT PANEL — compact: title, location, genre/tone, goal, begin scene */}
            <div
              className="flex w-[140px] flex-none flex-col overflow-hidden border-r p-[40px_10px_12px] sm:w-[158px] sm:p-[46px_14px_14px]"
              style={{ borderColor: HERO.divider }}
            >
              <h2
                className="line-clamp-2 font-display text-[15px] font-bold leading-[1.1] sm:text-[18px]"
                style={{ color: HERO.title }}
              >
                {s.title}
              </h2>

              {/* Location */}
              <div className="mt-[5px] flex items-baseline gap-[4px]">
                <span
                  className="flex-none font-mono text-[7.5px] uppercase tracking-[0.16em]"
                  style={{ color: HERO.label }}
                >
                  Location
                </span>
                <span
                  className="truncate font-mono text-[9px] font-medium"
                  style={{ color: HERO.title }}
                >
                  ◆ {s.setting.name}
                </span>
              </div>

              {/* Genre / tone tags */}
              <div className="mt-[6px] flex flex-wrap gap-[4px]">
                <span
                  className="rounded-[2px] px-[6px] py-[1px] font-mono text-[7.5px] uppercase tracking-[0.09em]"
                  style={{ background: HERO.label, color: "#1f160c" }}
                >
                  {s.genre}
                </span>
                <span
                  className="rounded-[2px] border px-[6px] py-[1px] font-mono text-[7.5px] uppercase tracking-[0.09em]"
                  style={{ color: HERO.toneText, borderColor: HERO.chevBd }}
                >
                  {s.tone}
                </span>
              </div>

              {/* Description — grows to fill remaining space */}
              <p
                className="mt-[7px] flex-1 overflow-hidden font-body text-[12px] leading-[1.4] line-clamp-3"
                style={{ color: HERO.goal }}
              >
                {s.goal}
              </p>

              {/* Begin Scene pinned to bottom */}
              {onBegin ? (
                <button
                  type="button"
                  onClick={() => onBegin(s.id)}
                  className="mt-[8px] w-full rounded-[2px] px-[4px] py-[7px] font-mono text-[8.5px] uppercase tracking-[0.09em] hover:brightness-110"
                  style={{ background: HERO.label, color: "#1f160c" }}
                >
                  Begin Scene ▸
                </button>
              ) : null}
            </div>

            {/* CHARACTER STRIP — wide horizontal scroll of vertical character cards */}
            <div
              className="flex min-w-0 flex-1 overflow-x-auto overflow-y-hidden"
              style={{ scrollbarWidth: "thin", scrollbarColor: `${HERO.label}44 transparent` }}
            >
              <div className="flex h-full items-stretch">
                {s.cast.map((c) => (
                  <div
                    key={c.id}
                    className="flex w-[88px] flex-none flex-col items-center border-r px-[6px] pb-[12px] pt-[42px] sm:w-[100px] sm:px-[8px] sm:pt-[48px]"
                    style={{ borderColor: HERO.divider }}
                  >
                    {/* Portrait */}
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
                          size={42}
                          ring={2}
                          bg={HERO.medBg}
                          src={c.portrait ? mediaUrl(c.portrait) : undefined}
                        />
                      </button>
                    ) : (
                      <Monogram
                        mono={c.mono}
                        color={c.color}
                        size={42}
                        ring={2}
                        bg={HERO.medBg}
                        src={c.portrait ? mediaUrl(c.portrait) : undefined}
                      />
                    )}

                    {/* Character name */}
                    <div
                      className="mt-[5px] w-full truncate text-center font-display text-[10px] font-semibold leading-[1.2] sm:text-[11px]"
                      style={{ color: c.color }}
                    >
                      {c.name}
                    </div>

                    {/* Divider */}
                    <div
                      className="mx-[4px] mt-[6px] w-full border-t"
                      style={{ borderColor: HERO.divider }}
                    />

                    {/* Stat rows: key label above value */}
                    <div className="mt-[5px] w-full flex-1 space-y-[5px] overflow-hidden">
                      {/* Role */}
                      <div>
                        <div
                          className="font-mono text-[6.5px] uppercase tracking-[0.1em]"
                          style={{ color: HERO.label }}
                        >
                          Role
                        </div>
                        <div
                          className="mt-[1px] line-clamp-2 font-mono text-[7px] leading-[1.25]"
                          style={{ color: HERO.toneText }}
                        >
                          {c.role}
                        </div>
                      </div>
                      {/* Traits */}
                      {c.traits ? (
                        <div>
                          <div
                            className="font-mono text-[6.5px] uppercase tracking-[0.1em]"
                            style={{ color: HERO.label }}
                          >
                            Traits
                          </div>
                          <div
                            className="mt-[1px] line-clamp-2 font-mono text-[7px] leading-[1.25]"
                            style={{ color: HERO.toneText }}
                          >
                            {c.traits}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
                {/* Trailing spacer so the last card doesn't clip against the art panel */}
                <div className="w-[8px] flex-none" />
              </div>
            </div>

            {/* SCENE ART — actual image, graceful placeholder fallback */}
            <div
              className="hidden aspect-[16/9] h-full w-auto flex-none overflow-hidden lg:flex"
              style={{ borderLeft: `1px solid ${HERO.border}` }}
            >
              {s.image ? (
                // eslint-disable-next-line @next/next/no-img-element -- generated scene art from our media mount
                <img
                  src={mediaUrl(s.image)}
                  alt={`Scene art for ${s.title}`}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div
                  className="flex h-full w-full items-center justify-center"
                  style={{ background: HERO.art }}
                >
                  <span
                    className="rounded-[2px] px-[9px] py-[3px] font-mono text-tag tracking-[0.1em]"
                    style={{ color: HERO.artLabel, background: HERO.artLabelBg }}
                  >
                    scene art
                  </span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* overlay: "Recent Scenario" label + chevrons + counter + edit button
          lg:right-[437px] keeps the overlay within the left+character zone,
          stopping before the scene art panel (246 × 16/9 ≈ 437px wide). */}
      <div className="pointer-events-none absolute top-[14px] left-[16px] right-[16px] flex items-center gap-3 sm:left-[30px] lg:right-[437px]">
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
        {/* Edit button — ml-auto, vertically centered with the label. */}
        {onEdit && current ? (
          <button
            type="button"
            onClick={() => onEdit(current.id)}
            aria-label={`Edit ${current.title}`}
            className="pointer-events-auto ml-auto flex h-[22px] w-[22px] items-center justify-center rounded-full text-[13px] leading-none"
            style={{ background: HERO.chev, border: `1px solid ${HERO.chevBd}`, color: HERO.label }}
          >
            ✎
          </button>
        ) : null}
      </div>

      {/* overlay: slide-select dots (left+character zone only at lg) */}
      <div className="absolute bottom-[16px] right-[16px] flex gap-[7px] lg:right-[437px]">
        {slides.map((s, i) => {
          const on = i === index;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => onSelect(s.id)}
              aria-label={`Show ${s.title}`}
              aria-current={on}
              className="h-[8px] rounded-full transition-all duration-300"
              style={{
                width: on ? 20 : 8,
                background: on ? HERO.label : "rgba(200,180,140,.5)",
              }}
            />
          );
        })}
      </div>
    </section>
  );
}
