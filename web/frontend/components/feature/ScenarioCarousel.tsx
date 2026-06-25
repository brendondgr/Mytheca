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
};

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
}: {
  slides: ResolvedScenario[];
  index: number;
  onPrev: () => void;
  onNext: () => void;
  onSelect: (id: string) => void;
  counterText: string;
  onBegin?: (id: string) => void;
  onProfile?: (id: string) => void;
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
            <div className="min-w-0 flex-1 p-[40px_18px_18px] sm:p-[46px_30px_22px]">
              <h2
                className="font-display text-[24px] font-bold leading-[1.05] sm:text-[32px]"
                style={{ color: HERO.title }}
              >
                {s.title}
              </h2>
              <div className="mt-[12px] flex gap-2">
                <span
                  className="rounded-[2px] px-[9px] py-[3px] font-mono text-[9.5px] uppercase tracking-[0.1em]"
                  style={{ background: HERO.label, color: "#1f160c" }}
                >
                  {s.genre}
                </span>
                <span
                  className="rounded-[2px] border px-[9px] py-[3px] font-mono text-[9.5px] uppercase tracking-[0.1em]"
                  style={{ color: HERO.toneText, borderColor: HERO.chevBd }}
                >
                  {s.tone}
                </span>
              </div>
              <p
                className="mt-[13px] max-w-[600px] font-body text-[15.5px] leading-[1.45]"
                style={{ color: HERO.goal }}
              >
                {s.goal}
              </p>
              <div className="mt-[18px] flex flex-wrap items-center gap-[14px] sm:gap-[18px]">
                <div className="flex items-center gap-[6px]">
                  {s.cast.map((c) =>
                    onProfile ? (
                      <button
                        key={c.id}
                        type="button"
                        onClick={() => onProfile(c.id)}
                        aria-label={`View ${c.name}`}
                        title={c.name}
                        className="rounded-full transition-transform hover:scale-110"
                      >
                        <Monogram mono={c.mono} color={c.color} size={34} ring={1.5} bg={HERO.medBg} src={c.portrait ? mediaUrl(c.portrait) : undefined} />
                      </button>
                    ) : (
                      <Monogram key={c.id} mono={c.mono} color={c.color} size={34} ring={1.5} bg={HERO.medBg} src={c.portrait ? mediaUrl(c.portrait) : undefined} />
                    ),
                  )}
                  <span className="ml-[8px] font-mono text-[10.5px]" style={{ color: HERO.set }}>
                    ◆ {s.setting.name}
                  </span>
                </div>
                {onBegin ? (
                  <button
                    type="button"
                    onClick={() => onBegin(s.id)}
                    className="ml-auto rounded-[2px] px-[20px] py-[10px] font-mono text-[11px] uppercase tracking-[0.1em] hover:brightness-110"
                    style={{ background: HERO.label, color: "#1f160c" }}
                  >
                    Begin Scene ▸
                  </button>
                ) : null}
              </div>
            </div>
            <div
              className="hidden aspect-[16/9] h-full w-auto flex-none items-center justify-center lg:flex"
              style={{ background: HERO.art, borderLeft: `1px solid ${HERO.border}` }}
            >
              <span
                className="rounded-[2px] px-[9px] py-[3px] font-mono text-[9.5px] tracking-[0.1em]"
                style={{ color: HERO.artLabel, background: HERO.artLabelBg }}
              >
                scene art
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* overlay: label + chevrons + counter */}
      <div className="pointer-events-none absolute top-[16px] right-[16px] left-[16px] flex items-center gap-3 sm:left-[30px] lg:right-[449px]">
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
      </div>

      {/* overlay: dots */}
      <div className="absolute right-[16px] bottom-[16px] flex gap-[7px] lg:right-[449px]">
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
