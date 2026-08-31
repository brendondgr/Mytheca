import { cn } from "@/lib/cn";
import { mediaUrl } from "@/lib/api";
import { CARD_SCRIM, OVER_ART } from "@/lib/cardArt";
import { Monogram } from "@/components/ui/Monogram";
import { SmartImage } from "@/components/ui/SmartImage";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { IconButton } from "@/components/ui/IconButton";
import { Icon } from "@/components/ui/Icon";
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
        "mytheca-card relative overflow-hidden rounded-sm hover-lift hover:shadow-[0_7px_18px_rgba(20,14,6,.18)]",
        hasImage && "min-h-[176px]",
        featured
          ? "border-2 border-accent shadow-[0_6px_18px_rgba(142,43,28,.16)]"
          : "border border-cardbd",
        !hasImage && (featured ? "bg-card2" : "bg-card"),
      )}
    >
      {hasImage ? (
        <>
          <SmartImage
            src={mediaUrl(s.image!)}
            alt={`Scene art for ${s.title}`}
            fill
            className="pointer-events-none"
          />
          <div
            aria-hidden
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
        className="absolute inset-0 z-0 cursor-pointer rounded-sm"
      />

      {/* One square, in the card's corner.
       *
       * The "Recent" badge that used to sit beside it is gone. It measured 91px with the
       * pencil, which is why the title needed a 92px reserve to clear it — a badge that
       * cost the title a fifth of its width to say something the card ALREADY says: it is
       * the featured card, drawn with a 2px accent border and an accent shadow. The
       * accessible answer is in `aria-pressed` on the select button below, which is where
       * a screen reader looks for it anyway. */}
      {onEdit ? (
        <div className="pointer-events-none absolute right-sm top-sm z-[2]">
          <IconButton
            label={`Edit ${s.title}`}
            onClick={onEdit}
            size={28}
            className="pointer-events-auto"
          >
            <Icon name="pencil" size={14} />
          </IconButton>
        </div>
      ) : null}

      <div className={cn("pointer-events-none relative z-[1]", featured ? "p-lg" : "p-lg")}>
        {/* The reserve clears the ACTUAL corner cluster, which is now one 28px square at
            `right-sm`: 28 + 8 + 8 = 44px, composed from scale steps rather than a measured
            literal so it stays on the system. It used to need 92px, because the cluster
            also held a "Recent" badge — an overlap is invisible to a `scrollWidth` gate and
            the first thing a person notices, so this number is not decorative. */}
        <h3
          className={cn(
            "font-display text-step-1 font-bold leading-[1.08]",
            !hasImage && "text-ink",
          )}
          style={{
            paddingInlineEnd: "calc(var(--sp-2xl) + var(--sp-sm) + var(--sp-sm))",
            ...(hasImage ? { color: OVER_ART.title } : {}),
          }}
        >
          {s.title}
        </h3>

        {/* Eyebrow + goal are width-capped on image cards so they stay over the
            dark side of the gradient and the art reads on the right. */}
        <div className={cn(hasImage && "max-w-[60%]")}>
          <Eyebrow
            tracking="0.1em"
            entity={hasImage ? OVER_ART.eyebrow : "#A8762A"}
            className="mt-xs block"
          >
            {s.genre} · {s.tone}
          </Eyebrow>
          <p
            className={cn(
              "mt-sm font-body text-body-sm leading-[1.4]",
              hasImage ? "line-clamp-3" : "text-ink-soft",
            )}
            style={hasImage ? { color: OVER_ART.body } : undefined}
          >
            {s.goal}
          </p>
        </div>

        <div
          className={cn("mt-lg flex items-center justify-between border-t pt-md")}
          style={{ borderColor: hasImage ? OVER_ART.hair : "var(--hair)" }}
        >
          <div className="flex items-center gap-2xs">
            {s.cast.map((c) =>
              onProfile ? (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => onProfile(c.id)}
                  aria-label={`View ${c.name}`}
                  title={c.name}
                  className="pointer-events-auto relative z-[2] rounded-full hover-grow"
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
