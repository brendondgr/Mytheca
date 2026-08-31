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
      className="rounded-sm border border-cardbd bg-card2 p-[16px_18px]"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Eyebrow tracking="0.18em" color="var(--accent)">
          The scene is set
        </Eyebrow>
        <div className="flex flex-wrap items-center gap-xs">
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

      <div className="mt-sm font-display text-step-2 font-semibold leading-[1.15] text-ink">
        ◆ {s.title}
        <span className="text-body-sm font-normal text-ink-soft">: {s.setting.name}</span>
        <span className="ml-sm font-mono text-eyebrow tracking-[0.12em] text-mute uppercase">
          {s.setting.type}
        </span>
      </div>
      {stateLine ? (
        <p className="mt-2xs font-body text-body-sm leading-[1.45] text-ink-soft">
          {stateLine}
        </p>
      ) : null}

      {s.goal ? (
        <div className="mt-md border-t border-hair pt-sm">
          <Eyebrow size={9} tracking="0.16em" className="mb-2xs block">
            Your aim
          </Eyebrow>
          <p className="font-body text-body-sm leading-[1.45] text-ink italic">
            {s.goal}
          </p>
        </div>
      ) : null}

      <div className="mt-md border-t border-hair pt-sm">
        <Eyebrow size={9} tracking="0.16em" className="mb-sm block">
          In the Scene
        </Eyebrow>
        <div className="flex flex-wrap gap-x-lg gap-y-sm">
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
                  <span className="block font-display text-body-sm leading-[1.05] font-semibold text-ink">
                    {c.name.split(",")[0]}
                  </span>
                  <Eyebrow size={9} tracking="0.08em" entity={c.color} className="block">
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
                className="flex items-center gap-sm rounded-xs px-2xs py-3xs hover:bg-hover"
              >
                {inner}
              </button>
            ) : (
              <span key={c.id} className="flex items-center gap-sm">
                {inner}
              </span>
            );
          })}
        </div>
      </div>
    </section>
  );
}
