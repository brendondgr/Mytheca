"use client";

/**
 * The "1 / 2" pager on a beat that has been re-rolled.
 *
 * A re-roll keeps the previous wording rather than overwriting it, so this is how the player
 * gets back to it — often the first take was the better one, and discovering that after the
 * fact is exactly why they are kept.
 *
 * The count is a polite live region: flipping takes swaps the prose above it, and a
 * screen-reader user needs to be told which version they are now on.
 */
export function BeatTakePager({
  count,
  active,
  onSelect,
  disabled = false,
  label = "this beat",
}: {
  count: number;
  /** Zero-based index of the take on screen. */
  active: number;
  onSelect: (take: number) => void;
  disabled?: boolean;
  label?: string;
}) {
  // One version is not a choice; showing a dead pager on every beat would be noise.
  if (count < 2) return null;

  const atStart = active <= 0;
  const atEnd = active >= count - 1;

  return (
    <span className="flex items-center gap-[3px]">
      <button
        type="button"
        onClick={() => onSelect(active - 1)}
        disabled={disabled || atStart}
        aria-label={`Previous version of ${label}`}
        className="flex h-[24px] w-[24px] items-center justify-center rounded-[3px] text-[11px] text-mute hover:bg-hover hover:text-accent disabled:cursor-not-allowed disabled:opacity-30"
      >
        <span aria-hidden>‹</span>
      </button>
      <span
        aria-live="polite"
        className="font-mono text-[9px] tracking-[0.06em] text-mute tabular-nums"
      >
        {active + 1} / {count}
      </span>
      <button
        type="button"
        onClick={() => onSelect(active + 1)}
        disabled={disabled || atEnd}
        aria-label={`Next version of ${label}`}
        className="flex h-[24px] w-[24px] items-center justify-center rounded-[3px] text-[11px] text-mute hover:bg-hover hover:text-accent disabled:cursor-not-allowed disabled:opacity-30"
      >
        <span aria-hidden>›</span>
      </button>
    </span>
  );
}
