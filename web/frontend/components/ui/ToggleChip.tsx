import { cn } from "@/lib/cn";

/** Selectable pill (cast / setting / type / event-tag pickers in editors). */
export function ToggleChip({
  selected,
  onClick,
  children,
  className,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        "inline-flex cursor-pointer items-center gap-[7px] rounded-full border px-3 py-[5px] text-left",
        selected
          ? "border-[1.5px] border-accent bg-card2 font-semibold text-accent hover:bg-hover"
          : "border-field-bd bg-field text-ink-soft hover:border-hair-strong hover:bg-hover hover:text-ink",
        className,
      )}
    >
      {children}
    </button>
  );
}
