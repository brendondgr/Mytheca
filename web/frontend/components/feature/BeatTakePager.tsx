"use client";

import { Icon } from "@/components/ui/Icon";

/**
 * The "1 / 2" pager on a beat that has been re-rolled.
 *
 * A re-roll keeps the previous wording rather than overwriting it, so this is how the player
 * gets back to it — often the first take was the better one, and discovering that after the
 * fact is exactly why they are kept.
 *
 * The count is a polite live region: flipping takes swaps the prose above it, and a
 * screen-reader user needs to be told which version they are now on.
 *
 * It shares the beat's control bar with {@link BeatControls}, and is the one thing in that
 * bar that is not an action — which is why the bar it lives in stays visible when a beat has
 * more than one take: "1 / 2" is state the player needs without hovering to ask for it.
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
    <span className="flex items-center gap-3xs">
      <button
        type="button"
        onClick={() => onSelect(active - 1)}
        disabled={disabled || atStart}
        aria-label={`Previous version of ${label}`}
        className="flex h-[44px] w-[44px] items-center justify-center rounded-xs text-mute hover:bg-hover hover:text-accent-ink disabled:cursor-not-allowed disabled:opacity-30 sm:h-[26px] sm:w-[26px]"
      >
        <Icon name="back" size={14} />
      </button>
      <span
        aria-live="polite"
        className="font-mono text-eyebrow tracking-[0.06em] text-mute tabular-nums"
      >
        {active + 1} / {count}
      </span>
      <button
        type="button"
        onClick={() => onSelect(active + 1)}
        disabled={disabled || atEnd}
        aria-label={`Next version of ${label}`}
        className="flex h-[44px] w-[44px] items-center justify-center rounded-xs text-mute hover:bg-hover hover:text-accent-ink disabled:cursor-not-allowed disabled:opacity-30 sm:h-[26px] sm:w-[26px]"
      >
        <Icon name="forward" size={14} />
      </button>
    </span>
  );
}
