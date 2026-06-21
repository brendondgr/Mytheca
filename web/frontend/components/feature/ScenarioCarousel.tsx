import { Monogram } from "@/components/ui/Monogram";
import type { ResolvedScenario } from "@/lib/types";

// Fixed "dark cinematic" hero palette (independent of the page theme, matching
// the reference). Theme-tuned variants are a later polish item.
const HERO = {
  panel: "linear-gradient(135deg,#2A2016 0%,#3A2C1A 60%,#4A331C 100%)",
  art: "repeating-linear-gradient(45deg,#33271a,#33271a 8px,#3c2f1f 8px,#3c2f1f 16px)",
  title: "#F1E2C2",
  goal: "#D4C3A0",
  label: "#C8862A",
  set: "#9C8862",
  medBg: "#1F1710",
  artLabel: "#8a724e",
  artLabelBg: "#2A2016",
  chev: "rgba(20,14,6,.35)",
  chevBd: "#6a5436",
};

/** The recent-scenario hero carousel (display + prev/next/dots navigation). */
export function ScenarioCarousel({
  slides,
  index,
  onPrev,
  onNext,
  onSelect,
  counterText,
}: {
  slides: ResolvedScenario[];
  index: number;
  onPrev: () => void;
  onNext: () => void;
  onSelect: (id: string) => void;
  counterText: string;
}) {
  return (
    <section
      aria-roledescription="carousel"
      aria-label="Recent scenarios"
      className="relative mx-[28px] mt-[18px] h-[246px] flex-none overflow-hidden rounded-[5px] shadow-[0_6px_22px_rgba(20,14,6,.18)]"
    >
      <div
        className="flex h-full transition-transform duration-[550ms] ease-[cubic-bezier(.45,.05,.2,1)]"
        style={{ transform: `translateX(-${index * 100}%)` }}
      >
        {slides.map((s, i) => (
          <div
            key={s.id}
            aria-hidden={i !== index}
            className="flex h-full flex-[0_0_100%]"
            style={{ background: HERO.panel, border: "1px solid #1c150c" }}
          >
            <div className="min-w-0 flex-1 p-[46px_30px_22px]">
              <h2
                className="font-display text-[32px] font-bold leading-[1.05]"
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
                  style={{ color: "#D8C29A", borderColor: HERO.chevBd }}
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
              <div className="mt-[18px] flex items-center gap-[6px]">
                {s.cast.map((c) => (
                  <Monogram
                    key={c.id}
                    mono={c.mono}
                    color={c.color}
                    size={34}
                    ring={1.5}
                    bg={HERO.medBg}
                  />
                ))}
                <span
                  className="ml-[8px] font-mono text-[10.5px]"
                  style={{ color: HERO.set }}
                >
                  ◆ {s.setting.name}
                </span>
              </div>
            </div>
            <div
              className="flex w-[200px] flex-none items-center justify-center"
              style={{ background: HERO.art, borderLeft: "1px solid #1c150c" }}
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
      <div className="pointer-events-none absolute top-[16px] right-[212px] left-[30px] flex items-center gap-3">
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
      <div className="absolute right-[212px] bottom-[16px] flex gap-[7px]">
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
