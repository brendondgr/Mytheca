import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { IconButton } from "@/components/ui/IconButton";
import { cn } from "@/lib/cn";
import type { Character } from "@/lib/types";

function Detail({
  label,
  color,
  children,
}: {
  label: string;
  color: string;
  children: React.ReactNode;
}) {
  return (
    <p className="font-body text-[13.5px] leading-[1.4] text-ink">
      <Eyebrow size={9} tracking="0.1em" color={color} className="mr-[6px]">
        {label}
      </Eyebrow>
      {children}
    </p>
  );
}

/**
 * Character card — an accessible disclosure: the summary (monogram + name +
 * traits) is a button that reveals voice/goal/secret. The optional edit pencil
 * is a sibling button (no nested interactives).
 */
export function CharacterCard({
  character,
  expanded,
  onToggle,
  onEdit,
  highlighted = false,
}: {
  character: Character;
  expanded: boolean;
  onToggle: () => void;
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
        onClick={onToggle}
        aria-expanded={expanded}
        className="block w-full cursor-pointer p-[15px] text-left"
      >
        <span className="flex items-center gap-3">
          <Monogram mono={c.mono} color={c.color} size={46} />
          <span className="min-w-0 pr-[18px]">
            <span className="block font-display text-[16px] font-semibold leading-[1.1] text-ink">
              {c.name}
            </span>
            <Eyebrow size={9} tracking="0.12em" color={c.color} className="mt-1 block">
              {c.role}
            </Eyebrow>
            {highlighted ? (
              <span className="mt-[3px] block font-mono text-[8.5px] uppercase tracking-[0.12em] text-accent">
                ◆ In this scene
              </span>
            ) : null}
          </span>
        </span>
        <span className="mt-[11px] block font-body text-[14px] italic leading-[1.35] text-ink-soft">
          {c.traits}
        </span>
      </button>
      {expanded ? (
        <div className="px-[15px] pb-[15px]">
          <div className="flex flex-col gap-[7px] border-t border-hair pt-[10px]">
            <Detail label="Voice" color="#A8762A">
              {c.speech}
            </Detail>
            <Detail label="Goal" color="#A8762A">
              {c.goal}
            </Detail>
            <Detail label="Secret" color="var(--accent)">
              {c.secret}
            </Detail>
          </div>
        </div>
      ) : null}
    </div>
  );
}
