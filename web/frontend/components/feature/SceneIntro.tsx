import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Tag } from "@/components/ui/Tag";
import { mediaUrl } from "@/lib/api";
import type { ResolvedScenario } from "@/lib/types";

/**
 * The scene-heading band at the top of the transcript — a manuscript-style
 * "scene is set" header that names the setting, genre/tone, the player's aim,
 * and the dramatis personae. It carries the same context the Library and the
 * side rails show, so the reading column reads as a complete scene on its own
 * (and stays informative when the rails collapse on mobile).
 */
export function SceneIntro({
  scenario,
  onProfile,
}: {
  scenario: ResolvedScenario;
  onProfile?: (id: string) => void;
}) {
  const s = scenario;
  const stateLine = s.setting.currentState || s.setting.desc;
  return (
    <section
      aria-label="Scene overview"
      className="rounded-[6px] border border-cardbd bg-card2 p-[16px_18px]"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Eyebrow tracking="0.18em" color="var(--accent)">
          The scene is set
        </Eyebrow>
        <div className="flex flex-wrap items-center gap-[6px]">
          {s.genre ? (
            <Tag variant="outline" tone="gold" pill>
              {s.genre}
            </Tag>
          ) : null}
          {s.tone ? (
            <Tag variant="outline" tone="neutral" pill>
              {s.tone}
            </Tag>
          ) : null}
        </div>
      </div>

      <div className="mt-[10px] font-display text-[20px] font-semibold leading-[1.15] text-ink">
        ◆ {s.title}: {s.setting.name}
        <span className="ml-[8px] font-mono text-[11px] tracking-[0.12em] text-mute uppercase">
          {s.setting.type}
        </span>
      </div>
      {stateLine ? (
        <p className="mt-[5px] font-body text-[15px] leading-[1.45] text-ink-soft">
          {stateLine}
        </p>
      ) : null}

      {s.goal ? (
        <div className="mt-[12px] border-t border-hair pt-[10px]">
          <Eyebrow size={9} tracking="0.16em" className="mb-[4px] block">
            Your aim
          </Eyebrow>
          <p className="font-body text-[15.5px] leading-[1.45] text-ink italic">
            {s.goal}
          </p>
        </div>
      ) : null}

      <div className="mt-[12px] border-t border-hair pt-[10px]">
        <Eyebrow size={9} tracking="0.16em" className="mb-[8px] block">
          At the table
        </Eyebrow>
        <div className="flex flex-wrap gap-x-[16px] gap-y-[8px]">
          {s.cast.map((c) => {
            const inner = (
              <>
                <Monogram
                  mono={c.mono}
                  color={c.color}
                  src={c.portrait ? mediaUrl(c.portrait) : undefined}
                  size={32}
                  ring={1.5}
                  fontSize={11}
                />
                <span className="min-w-0 text-left">
                  <span className="block font-display text-[14.5px] leading-[1.05] font-semibold text-ink">
                    {c.name.split(",")[0]}
                  </span>
                  <Eyebrow size={9} tracking="0.08em" color={c.color} className="block">
                    {c.role}
                  </Eyebrow>
                </span>
              </>
            );
            return onProfile ? (
              <button
                key={c.id}
                type="button"
                onClick={() => onProfile(c.id)}
                aria-label={`View ${c.name}`}
                title={c.name}
                className="flex items-center gap-[8px] rounded-[3px] hover:opacity-80"
              >
                {inner}
              </button>
            ) : (
              <span key={c.id} className="flex items-center gap-[8px]">
                {inner}
              </span>
            );
          })}
        </div>
      </div>
    </section>
  );
}
