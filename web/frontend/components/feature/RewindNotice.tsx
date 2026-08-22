"use client";

/**
 * The quiet rule at the foot of a transcript that was just rewound.
 *
 * A rewind silently removes half the page, which without a marker reads as a bug. This says
 * what happened, and — because the removed history was forked into its own play-through
 * rather than deleted — offers the way back.
 *
 * `role="status"` so a screen reader is told the scene changed under it; the visual change
 * is the *only* other signal, and it is one a non-sighted reader cannot receive.
 */
export function RewindNotice({
  removedEvents,
  onUndo,
  onDismiss,
}: {
  removedEvents: number;
  /** Open the snapshot play-through. Omitted when the rewind kept none. */
  onUndo?: () => void;
  onDismiss: () => void;
}) {
  return (
    <div
      role="status"
      className="my-[6px] flex flex-wrap items-center justify-center gap-[10px] border-t border-hair pt-[10px]"
    >
      <span className="font-mono text-[9px] tracking-[0.14em] text-mute2 uppercase">
        — rewound{removedEvents > 0 ? ` · ${removedEvents} beats removed` : ""} · say what
        happens instead —
      </span>
      {onUndo ? (
        <button
          type="button"
          onClick={onUndo}
          className="rounded-[3px] px-[7px] py-[3px] font-mono text-[9px] tracking-[0.1em] text-accent uppercase underline-offset-2 hover:bg-hover hover:underline"
        >
          Undo
        </button>
      ) : null}
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss the rewind notice"
        className="flex h-[24px] w-[24px] items-center justify-center rounded-[3px] text-[12px] text-mute hover:bg-hover hover:text-ink"
      >
        <span aria-hidden>×</span>
      </button>
    </div>
  );
}
