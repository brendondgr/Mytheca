import { cn } from "@/lib/cn";

/** The × dismiss control used in modal headers.
 *
 * The glyph itself is only ~20px, so it carries `.touch-target-overlay` to
 * reach 44x44 on coarse pointers without growing the header row on desktop.
 * The hover scale is gated by `.hover-lift`'s media query rather than applied
 * unconditionally — an un-gated `hover:scale-110` sticks after a tap on touch,
 * leaving a permanently enlarged × until the user taps elsewhere. */
export function CloseButton({
  onClose,
  className,
  disabled,
}: {
  onClose: () => void;
  className?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClose}
      disabled={disabled}
      aria-label="Close"
      className={cn(
        "inline-flex cursor-pointer items-center justify-center text-step-2 leading-none text-mute",
        "touch-target-overlay press close-button-hover",
        "enabled:hover:text-accent-ink",
        "disabled:cursor-not-allowed disabled:opacity-45",
        className,
      )}
    >
      ×
    </button>
  );
}
