import { cn } from "@/lib/cn";

/** The × dismiss control used in modal headers. */
export function CloseButton({
  onClose,
  className,
}: {
  onClose: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClose}
      aria-label="Close"
      className={cn(
        "cursor-pointer text-[20px] leading-none text-mute hover:scale-110 hover:text-accent",
        className,
      )}
    >
      ×
    </button>
  );
}
