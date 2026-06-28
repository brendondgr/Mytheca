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
  set: "var(--mute)",
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

// Scene art column: aspect-[16/9] h-[246px] → width ≈ 437px. Used to position
// the header overlay and dot pagination so they stop before the art panel.
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
          className="font-mono text-[9.5px] uppercase tracking-[0.22em]"
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
            {/* Left column: title + setting location + description */}
            <div className="min-w-0 flex-1 overflow-hidden p-[40px_16px_16px] sm:p-[46px_22px_18px]">
              <h2
                className="truncate font-display text-[22px] font-bold leading-[1.05] sm:text-[28px]"
                style={{ color: HERO.title }}
              >
                {s.title}
              </h2>

              {/* Genre / tone tags */}
              <div className="mt-[8px] flex gap-[6px]">
                <span
                  className="rounded-[2px] px-[8px] py-[2px] font-mono text-[9px] uppercase tracking-[0.1em]"
                  style={{ background: HERO.label, color: "#1f160c" }}
                >
                  {s.genre}
                </span>
                <span
                  className="rounded-[2px] border px-[8px] py-[2px] font-mono text-[9px] uppercase tracking-[0.1em]"
                  style={{ color: HERO.toneText, borderColor: HERO.chevBd }}
                >
                  {s.tone}
                </span>
              </div>

              {/* Setting — prominent location indicator below the title */}
              <div className="mt-[10px] flex items-baseline gap-[6px]">
                <span
                  className="flex-none font-mono text-[8px] uppercase tracking-[0.18em]"
                  style={{ color: HERO.label }}
                >
                  Location
                </span>
                <span
                  className="truncate font-mono text-[10.5px] font-medium"
                  style={{ color: HERO.title }}
                >
                  ◆ {s.setting.name}
                </span>
              </div>

              {/* Description / goal — capped to 2 lines */}
              <p
                className="mt-[8px] line-clamp-2 font-body text-[13.5px] leading-[1.4]"
                style={{ color: HERO.goal }}
              >
                {s.goal}
              </p>
            </div>

            {/* Middle column: cast with role/trait stats + Begin Scene */}
            <div
              className="hidden sm:flex w-[168px] flex-none flex-col border-l p-[40px_12px_12px] lg:w-[186px] lg:p-[46px_14px_14px]"
              style={{ borderColor: HERO.divider }}
            >
              <div className="flex flex-1 flex-col gap-[8px] overflow-hidden">
                {s.cast.slice(0, 3).map((c) => (
                  <div key={c.id} className="flex min-w-0 items-start gap-[7px]">
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
                          size={26}
                          ring={1.5}
                          bg={HERO.medBg}
                          src={c.portrait ? mediaUrl(c.portrait) : undefined}
                        />
                      </button>
                    ) : (
                      <div className="flex-none">
                        <Monogram
                          mono={c.mono}
                          color={c.color}
                          size={26}
                          ring={1.5}
                          bg={HERO.medBg}
                          src={c.portrait ? mediaUrl(c.portrait) : undefined}
                        />
                      </div>
                    )}
                    <div className="min-w-0 flex-1 pt-[1px]">
                      <div
                        className="truncate font-display text-[10.5px] font-semibold leading-[1.15]"
                        style={{ color: c.color }}
                      >
                        {c.name}
                      </div>
                      <div className="mt-[2px] flex items-baseline gap-[2px] truncate">
                        <span
                          className="flex-none font-mono text-[7px] uppercase tracking-[0.07em]"
                          style={{ color: HERO.statKey }}
                        >
                          Role —
                        </span>
                        <span
                          className="truncate font-mono text-[7px]"
                          style={{ color: HERO.toneText }}
                        >
                          {c.role}
                        </span>
                      </div>
                      {c.traits ? (
                        <div className="flex items-baseline gap-[2px] truncate">
                          <span
                            className="flex-none font-mono text-[7px] uppercase tracking-[0.07em]"
                            style={{ color: HERO.statKey }}
                          >
                            Traits —
                          </span>
                          <span
                            className="truncate font-mono text-[7px]"
                            style={{ color: HERO.toneText }}
                          >
                            {c.traits}
                          </span>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>

              {onBegin ? (
                <button
                  type="button"
                  onClick={() => onBegin(s.id)}
                  className="mt-[8px] w-full rounded-[2px] px-[8px] py-[8px] font-mono text-[10px] uppercase tracking-[0.1em] hover:brightness-110"
                  style={{ background: HERO.label, color: "#1f160c" }}
                >
                  Begin Scene ▸
                </button>
              ) : null}
            </div>

            {/* Right column: scene art (actual image or hatched placeholder) */}
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
                    className="rounded-[2px] px-[9px] py-[3px] font-mono text-[9.5px] tracking-[0.1em]"
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
          lg:right-[437px] keeps the overlay within the narrative+cast columns,
          stopping before the scene art panel (246px × 16/9 ≈ 437px wide). */}
      <div className="pointer-events-none absolute top-[14px] left-[16px] right-[16px] flex items-center gap-3 sm:left-[30px] lg:right-[437px]">
        <span
          className="font-mono text-[9.5px] uppercase tracking-[0.22em]"
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
          <span className="font-mono text-[9.5px]" style={{ color: HERO.label }}>
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
        {/* Edit button — ml-auto pushes it to the right edge of the overlay,
            vertically centered with the "Recent Scenario" label via items-center. */}
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

      {/* overlay: slide-select dots */}
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
