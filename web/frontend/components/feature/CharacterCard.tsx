import { Monogram } from "@/components/ui/Monogram";
import { SmartImage } from "@/components/ui/SmartImage";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { IconButton } from "@/components/ui/IconButton";
import { mediaUrl } from "@/lib/api";
import { PORTRAIT_SCRIM, OVER_ART } from "@/lib/cardArt";
import { cn } from "@/lib/cn";
import type { Character } from "@/lib/types";

/**
 * Character card — a tall, portrait-dominant tile (2:3) framed in the character's
 * own color so the picture is the focus. The portrait fills the card behind a
 * bottom scrim that carries the name + role; with no portrait it falls back to a
 * large centered monogram on a solid surface. Clicking the card opens the profile
 * modal (a single stretched button); the edit pencil is a sibling above it (no
 * nested interactives). Cast members of the selected scenario are lit with an
 * animated glow in the character's own color + "◆ In this scene" label
 * (never color alone).
 */
export function CharacterCard({
  character,
  onPreview,
  onEdit,
  highlighted = false,
}: {
  character: Character;
  /** Opens the character profile modal. */
  onPreview: () => void;
  onEdit?: () => void;
  /** Lit up when this character is in the selected scenario's cast. */
  highlighted?: boolean;
}) {
  const c = character;
  const hasPortrait = Boolean(c.portrait);
  return (
    <div
      className={cn(
        "mytheca-card group relative aspect-[2/3] overflow-hidden rounded-[4px] hover-lift hover:shadow-[0_8px_20px_rgba(20,14,6,.22)]",
        !hasPortrait && "bg-card2",
        highlighted && "mytheca-glow",
      )}
      style={{
        border: `2px solid ${c.color}`,
        ...(highlighted ? { "--glow-color": c.color } : {}),
      }}
    >
      <SmartImage
        src={hasPortrait ? mediaUrl(c.portrait!) : null}
        alt={`Portrait of ${c.name}`}
        fill
        className="pointer-events-none"
        placeholder={
          <div className="flex h-full w-full items-center justify-center pb-[64px]">
            <Monogram mono={c.mono} color={c.color} size={96} ring={2} fontSize={36} />
          </div>
        }
      />
      {hasPortrait ? (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{ background: PORTRAIT_SCRIM }}
        />
      ) : null}

      {/* Whole-card affordance: open the profile. */}
      <button
        type="button"
        onClick={onPreview}
        aria-label={`View ${c.name}`}
        className="absolute inset-0 z-0 cursor-pointer rounded-[4px]"
      />

      {/* Edit pencil (top-right) — sibling above the stretched button. */}
      {onEdit ? (
        <IconButton
          label={`Edit ${c.name}`}
          onClick={onEdit}
          className="absolute right-[10px] top-[10px] z-[2]"
        >
          ✎
        </IconButton>
      ) : null}

      {/* Footer band: name + role (+ cast badge). Over art it sits on the scrim
          with light text; without art it uses theme ink on the solid surface. */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[1] p-[12px_13px_13px]">
        {highlighted ? (
          <span
            className="mb-[5px] block font-mono text-[8.5px] uppercase tracking-[0.12em]"
            style={{ color: hasPortrait ? OVER_ART.accent : "var(--accent)" }}
          >
            ◆ In this scene
          </span>
        ) : null}
        <span
          className={cn(
            "block font-display text-[16px] font-semibold leading-[1.1]",
            !hasPortrait && "text-ink",
          )}
          style={hasPortrait ? { color: OVER_ART.title } : undefined}
        >
          {c.name}
        </span>
        <Eyebrow
          tracking="0.12em"
          color={hasPortrait ? OVER_ART.eyebrow : c.color}
          className="mt-[3px] block"
        >
          {c.role}
        </Eyebrow>
      </div>
    </div>
  );
}
