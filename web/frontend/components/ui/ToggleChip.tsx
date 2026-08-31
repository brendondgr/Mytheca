import { cn } from "@/lib/cn";

/** Selectable pill (cast / setting / type / event-tag pickers in editors).
 *
 * `aria-pressed` carries the selected state; the border weight and fill carry
 * it visually, so selection is never signalled by colour alone. */
export function ToggleChip({
  selected,
  onClick,
  children,
  className,
  disabled,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
  className?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={selected}
      className={cn(
        "inline-flex cursor-pointer items-center gap-xs rounded-full border px-3 py-2xs text-left",
        "touch-target press",
        selected
          ? "border-[1.5px] border-accent bg-card2 font-semibold text-accent-ink enabled:hover:bg-hover"
          : "border-field-bd bg-field text-ink-soft enabled:hover:border-hair-strong enabled:hover:bg-hover enabled:hover:text-ink",
        "disabled:cursor-not-allowed disabled:opacity-45",
        className,
      )}
    >
      {children}
    </button>
  );
}
