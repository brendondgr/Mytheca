import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { IconButton } from "@/components/ui/IconButton";
import { mediaUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { Character } from "@/lib/types";

/**
 * Character card — clicking the card body opens the character profile modal.
 * The optional edit pencil (top-right) is a sibling button (no nested interactives).
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
  return (
    <div
      className={cn(
        "velora-card relative rounded-[3px] border hover:-translate-y-[2px] hover:shadow-[0_7px_18px_rgba(20,14,6,.18)]",
        highlighted
          ? "border-accent bg-card2 shadow-[0_4px_14px_rgba(142,43,28,.16)]"
          : "border-cardbd bg-card",
      )}
    >
      {onEdit ? (
        <IconButton
          label={`Edit ${c.name}`}
          onClick={onEdit}
          className="absolute right-[10px] top-[10px] z-[2]"
        >
          ✎
        </IconButton>
      ) : null}
      <button
        type="button"
        onClick={onPreview}
        className="block w-full cursor-pointer p-[15px] text-left"
      >
        <span className="flex items-center gap-3">
          <Monogram
            mono={c.mono}
            color={c.color}
            size={46}
            src={c.portrait ? mediaUrl(c.portrait) : undefined}
          />
          <span className="min-w-0 pr-[18px]">
            <span className="block font-display text-[16px] font-semibold leading-[1.1] text-ink">
              {c.name}
            </span>
            <Eyebrow tracking="0.12em" color={c.color} className="mt-1 block">
              {c.role}
            </Eyebrow>
            {highlighted ? (
              <span className="mt-[3px] block font-mono text-eyebrow uppercase tracking-[0.12em] text-accent">
                ◆ In this scene
              </span>
            ) : null}
          </span>
        </span>
        <span className="mt-[11px] block font-body text-body-sm italic leading-[1.35] text-ink-soft">
          {c.traits}
        </span>
      </button>
    </div>
  );
}
