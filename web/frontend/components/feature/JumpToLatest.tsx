import { cn } from "@/lib/cn";

/**
 * The way back to the live edge of a scene.
 *
 * This is the other half of not auto-scrolling a reader who has scrolled up:
 * without it, stopping the auto-scroll would just strand them. It appears only
 * while they are detached, sits above the composer, and is a real button — so
 * a keyboard user can return to the newest beat without scrolling by hand.
 */
export function JumpToLatest({
  onClick,
  className,
}: {
  onClick: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "pointer-events-none absolute inset-x-0 bottom-[10px] flex justify-center",
        className,
      )}
    >
      <button
        type="button"
        onClick={onClick}
        className="content-enter press touch-target pointer-events-auto inline-flex cursor-pointer items-center gap-[7px] rounded-full border border-menu-bd bg-menu px-[14px] py-[7px] font-mono text-[10.5px] tracking-[0.1em] text-ink uppercase shadow-[0_6px_18px_rgba(10,6,2,.35)] transition-colors duration-fast ease-soft hover:border-accent hover:text-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        <span aria-hidden>↓</span>
        Jump to latest
      </button>
    </div>
  );
}
