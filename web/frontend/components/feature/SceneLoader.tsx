import { Eyebrow } from "@/components/ui/Eyebrow";
import { Monogram } from "@/components/ui/Monogram";
import { mediaUrl } from "@/lib/api";
import { CARD_SCRIM, OVER_ART } from "@/lib/cardArt";
import type { ResolvedScenario } from "@/lib/types";

/**
 * The "conjuring the scene" curtain: a full-screen establishing screen shown
 * while the scene loads. It carries the scenario's context — scene art, setting,
 * cast, genre/tone, and goal — so entering a scene reads like raising a curtain
 * on the world rather than a blank spinner. Dissolves into the live transcript.
 */
export function SceneLoader({
  scenario,
  storylineName,
  visible,
}: {
  scenario: ResolvedScenario;
  storylineName?: string;
  visible: boolean;
}) {
  if (!visible) return null;
  const s = scenario;
  const hasArt = Boolean(s.image);
  const kicker = storylineName ? `Entering ${storylineName}` : "Entering the scene";

  return (
    <div
      role="status"
      aria-label={`Loading the scene: ${s.title}`}
      className="velora-page fixed inset-0 z-[80] flex items-center justify-center overflow-hidden p-6"
    >
      {/* Scene-art backdrop (gradient fallback when no image), behind a scrim. */}
      {hasArt ? (
        // eslint-disable-next-line @next/next/no-img-element -- generated scene art from our media mount
        <img
          src={mediaUrl(s.image ?? "")}
          alt=""
          aria-hidden
          className="pointer-events-none absolute inset-0 h-full w-full object-cover"
        />
      ) : null}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{ background: hasArt ? CARD_SCRIM : undefined }}
      />

      <div
        className="relative z-[1] w-full max-w-[560px] motion-safe:animate-[embPop_.5s_ease-out]"
        style={hasArt ? { color: OVER_ART.title } : undefined}
      >
        <Eyebrow
          tracking="0.24em"
          color={hasArt ? OVER_ART.eyebrow : "#A8762A"}
          className="block"
        >
          {kicker}
        </Eyebrow>

        <h2
          className="mt-[10px] font-display text-[30px] leading-[1.1] font-bold tracking-[0.02em] sm:text-[36px]"
          style={{ color: hasArt ? OVER_ART.title : "var(--ink)" }}
        >
          {s.title}
        </h2>

        <div
          className="mt-[10px] flex flex-wrap items-center gap-x-[10px] gap-y-[4px] font-mono text-[10px] tracking-[0.14em] uppercase"
          style={{ color: hasArt ? OVER_ART.meta : "var(--mute)" }}
        >
          <span>◆ {s.setting.name}</span>
          {s.genre ? <span>· {s.genre}</span> : null}
          {s.tone ? <span>· {s.tone}</span> : null}
        </div>

        {/* Cast assembling at the table. */}
        <div className="mt-[22px]">
          <Eyebrow
            tracking="0.18em"
            color={hasArt ? OVER_ART.eyebrow : "var(--mute2)"}
            className="mb-[10px] block"
          >
            The cast gathers
          </Eyebrow>
          <div className="flex flex-wrap items-center gap-[14px]">
            {s.cast.map((c) => (
              <div key={c.id} className="flex items-center gap-[9px]">
                <Monogram
                  mono={c.mono}
                  color={c.color}
                  src={c.portrait ? mediaUrl(c.portrait) : undefined}
                  size={36}
                  ring={1.5}
                  fontSize={13}
                />
                <span className="min-w-0">
                  <span
                    className="block font-display text-[14px] leading-[1.05] font-semibold"
                    style={{ color: hasArt ? OVER_ART.title : "var(--ink)" }}
                  >
                    {c.name.split(",")[0]}
                  </span>
                  <Eyebrow
                    size={8}
                    tracking="0.08em"
                    color={hasArt ? OVER_ART.eyebrow : c.color}
                    className="mt-[2px] block"
                  >
                    {c.role}
                  </Eyebrow>
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Scene goal. */}
        {s.goal ? (
          <div className="mt-[22px]">
            <Eyebrow
              tracking="0.18em"
              color={hasArt ? OVER_ART.eyebrow : "var(--mute2)"}
              className="mb-[6px] block"
            >
              Your aim
            </Eyebrow>
            <p
              className="max-w-[460px] font-body text-[15px] leading-[1.5] italic"
              style={{ color: hasArt ? OVER_ART.body : "var(--ink-soft)" }}
            >
              {s.goal}
            </p>
          </div>
        ) : null}

        {/* Conjuring progress. */}
        <div className="mt-[26px] flex items-center gap-[12px]">
          <div className="relative h-[26px] w-[26px] flex-none">
            <div className="absolute inset-0 animate-[embSpin_1s_linear_infinite] rounded-full border-[2.5px] border-cardbd border-t-accent motion-reduce:animate-none" />
            <div className="absolute inset-0 flex items-center justify-center text-[12px] text-accent">
              ❖
            </div>
          </div>
          <div
            className="font-mono text-[10px] tracking-[0.16em] uppercase"
            style={{ color: hasArt ? OVER_ART.meta : "var(--mute)" }}
          >
            Conjuring the scene
            <span className="animate-[embDots_1.4s_infinite] motion-reduce:hidden">.</span>
            <span className="animate-[embDots_1.4s_infinite_.2s] motion-reduce:hidden">.</span>
            <span className="animate-[embDots_1.4s_infinite_.4s] motion-reduce:hidden">.</span>
          </div>
        </div>
      </div>
    </div>
  );
}
