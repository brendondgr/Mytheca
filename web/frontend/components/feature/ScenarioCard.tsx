import { cn } from "@/lib/cn";
import { mediaUrl } from "@/lib/api";
import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { IconButton } from "@/components/ui/IconButton";
import type { ResolvedScenario } from "@/lib/types";

/**
 * Scenario card. The whole card is a single "feature this scenario" button
 * (stretched, behind the content); secondary actions (edit, cast profiles) sit
 * above it with `pointer-events-auto`, avoiding nested interactive elements.
 */
export function ScenarioCard({
  scenario,
  featured,
  onSelect,
  onEdit,
  onProfile,
}: {
  scenario: ResolvedScenario;
  featured: boolean;
  onSelect: () => void;
  onEdit?: () => void;
  onProfile?: (id: string) => void;
}) {
  const s = scenario;
  return (
    <div
      className={cn(
        "velora-card relative rounded-[4px] hover:-translate-y-[2px] hover:shadow-[0_7px_18px_rgba(20,14,6,.18)]",
        featured
          ? "border-2 border-accent bg-card2 p-[15px] shadow-[0_6px_18px_rgba(142,43,28,.16)]"
          : "border border-cardbd bg-card p-[16px]",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={featured}
        aria-label={`Feature scenario ${s.title}`}
        className="absolute inset-0 z-0 cursor-pointer rounded-[4px]"
      />
      {onEdit ? (
        <IconButton
          label={`Edit ${s.title}`}
          onClick={onEdit}
          className="absolute right-[10px] top-[10px] z-[2]"
        >
          ✎
        </IconButton>
      ) : null}
      {s.image ? (
        // eslint-disable-next-line @next/next/no-img-element -- generated scene art from our media mount
        <img
          src={mediaUrl(s.image)}
          alt={`Scene art for ${s.title}`}
          className="pointer-events-none relative z-[1] -mx-[16px] -mt-[15px] mb-[12px] h-[96px] w-[calc(100%+32px)] object-cover"
        />
      ) : null}
      <div className="pointer-events-none relative z-[1]">
        <div className="flex items-baseline justify-between gap-[10px] pr-[22px]">
          <h3 className="font-display text-[19px] font-bold leading-[1.08] text-ink">
            {s.title}
          </h3>
          {featured ? (
            <span className="rounded-full bg-accent px-[7px] py-[2px] font-mono text-[8px] uppercase tracking-[0.1em] whitespace-nowrap text-[#F6ECDA]">
              Recent
            </span>
          ) : null}
        </div>
        <Eyebrow size={9} tracking="0.1em" color="#A8762A" className="mt-[6px] block">
          {s.genre} · {s.tone}
        </Eyebrow>
        <p className="mt-[9px] font-body text-[14px] leading-[1.4] text-ink-soft">
          {s.goal}
        </p>
        <div className="mt-[14px] flex items-center justify-between border-t border-hair pt-[11px]">
          <div className="flex items-center gap-[5px]">
            {s.cast.map((c) =>
              onProfile ? (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => onProfile(c.id)}
                  aria-label={`View ${c.name}`}
                  title={c.name}
                  className="pointer-events-auto relative z-[2] rounded-full transition-transform hover:scale-110"
                >
                  <Monogram mono={c.mono} color={c.color} size={27} src={c.portrait ? mediaUrl(c.portrait) : undefined} />
                </button>
              ) : (
                <Monogram key={c.id} mono={c.mono} color={c.color} size={27} src={c.portrait ? mediaUrl(c.portrait) : undefined} />
              ),
            )}
          </div>
          <span className="font-body text-[13px] text-ink-soft">◆ {s.setting.name}</span>
        </div>
      </div>
    </div>
  );
}
