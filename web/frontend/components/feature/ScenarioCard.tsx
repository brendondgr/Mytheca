import { cn } from "@/lib/cn";
import { mediaUrl } from "@/lib/api";
import { CARD_SCRIM, OVER_ART } from "@/lib/cardArt";
import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { IconButton } from "@/components/ui/IconButton";
import type { ResolvedScenario } from "@/lib/types";

/**
 * Scenario card. When the scenario has scene art the image fills the whole card
 * behind a left-dark→right-bright gradient "filter" (text on the dark left, art
 * reading on the right); otherwise it falls back to a solid, theme-aware card.
 * The whole card is a single "feature this scenario" button (stretched, behind
 * the content); secondary actions (edit, cast profiles) sit above it with
 * `pointer-events-auto`, avoiding nested interactive elements.
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
  const hasImage = !!s.image;
  return (
    <div
      className={cn(
        "mytheca-card relative overflow-hidden rounded-[4px] hover:-translate-y-[2px] hover:shadow-[0_7px_18px_rgba(20,14,6,.18)]",
        hasImage && "min-h-[176px]",
        featured
          ? "border-2 border-accent shadow-[0_6px_18px_rgba(142,43,28,.16)]"
          : "border border-cardbd",
        !hasImage && (featured ? "bg-card2" : "bg-card"),
      )}
    >
      {hasImage ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element -- generated scene art from our media mount */}
          <img
            src={mediaUrl(s.image!)}
            alt={`Scene art for ${s.title}`}
            className="pointer-events-none absolute inset-0 h-full w-full object-cover"
          />
          <div
            className="pointer-events-none absolute inset-0"
            style={{ background: CARD_SCRIM }}
          />
        </>
      ) : null}

      <button
        type="button"
        onClick={onSelect}
        aria-pressed={featured}
        aria-label={`Feature scenario ${s.title}`}
        className="absolute inset-0 z-0 cursor-pointer rounded-[4px]"
      />

      {/* Top-right cluster: Recent badge + edit pencil, grouped so they never
          overlap when both are present. */}
      {featured || onEdit ? (
        <div className="pointer-events-none absolute right-[10px] top-[10px] z-[2] flex items-center gap-[6px]">
          {featured ? (
            <span className="rounded-full bg-accent px-[7px] py-[2px] font-mono text-[8px] uppercase tracking-[0.1em] whitespace-nowrap text-[#F6ECDA]">
              Recent
            </span>
          ) : null}
          {onEdit ? (
            <IconButton label={`Edit ${s.title}`} onClick={onEdit} className="pointer-events-auto">
              ✎
            </IconButton>
          ) : null}
        </div>
      ) : null}

      <div className={cn("pointer-events-none relative z-[1]", featured ? "p-[15px]" : "p-[16px]")}>
        <h3
          className={cn(
            "pr-[92px] font-display text-[19px] font-bold leading-[1.08]",
            !hasImage && "text-ink",
          )}
          style={hasImage ? { color: OVER_ART.title } : undefined}
        >
          {s.title}
        </h3>

        {/* Eyebrow + goal are width-capped on image cards so they stay over the
            dark side of the gradient and the art reads on the right. */}
        <div className={cn(hasImage && "max-w-[60%]")}>
          <Eyebrow
            tracking="0.1em"
            color={hasImage ? OVER_ART.eyebrow : "#A8762A"}
            className="mt-[6px] block"
          >
            {s.genre} · {s.tone}
          </Eyebrow>
          <p
            className={cn(
              "mt-[9px] font-body text-body-sm leading-[1.4]",
              hasImage ? "line-clamp-3" : "text-ink-soft",
            )}
            style={hasImage ? { color: OVER_ART.body } : undefined}
          >
            {s.goal}
          </p>
        </div>

        <div
          className={cn("mt-[14px] flex items-center justify-between border-t pt-[11px]")}
          style={{ borderColor: hasImage ? OVER_ART.hair : "var(--hair)" }}
        >
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
          <span
            className={cn("font-body text-body-sm", !hasImage && "text-ink-soft")}
            style={hasImage ? { color: OVER_ART.meta } : undefined}
          >
            ◆ {s.setting.name}
          </span>
        </div>
      </div>
    </div>
  );
}
