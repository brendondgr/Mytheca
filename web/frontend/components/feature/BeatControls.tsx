"use client";

import { useState } from "react";

/**
 * The per-beat control cluster: what the player can do to a beat that has already landed.
 *
 * Visibility is `opacity-0` until the beat is hovered **or contains focus** — never
 * `display: none`. A hidden control is out of the tab order, which would make every one of
 * these mouse-only; this way the cluster is always reachable by keyboard and merely quiet
 * until you are looking at that beat.
 *
 * Rewind confirms in place, because it removes content. Branch does not, because it removes
 * nothing — that asymmetry is the point: the non-destructive way to explore is the one that
 * costs a single click.
 */
export function BeatControls({
  onEdit,
  onReroll,
  onBranch,
  onRewind,
  rewindBeatCount,
  disabled = false,
  label = "this beat",
}: {
  /** Rewrite this beat's prose. Omit for a beat that has none (a stat change, choices). */
  onEdit?: () => void;
  /**
   * Ask for another version. `scope: "turn"` replays the whole turn the beat belongs to —
   * a beat that went wrong because the *turn* went wrong is not fixed by re-rolling one
   * line of it. Omit for a beat that cannot be re-generated.
   */
  onReroll?: (scope: "beat" | "turn") => void;
  /** Fork the play-through here, leaving the original intact. Omit to hide. */
  onBranch?: () => void;
  /** Cut the play-through back to here. Omit to hide. */
  onRewind?: () => void;
  /** How many beats a rewind would remove — named in the confirmation, never guessed at. */
  rewindBeatCount?: number;
  /** True while a turn is streaming: the record must not be edited mid-sentence. */
  disabled?: boolean;
  /** What this beat is, for the controls' accessible names. */
  label?: string;
}) {
  const [confirming, setConfirming] = useState(false);

  if (!onEdit && !onReroll && !onBranch && !onRewind) return null;

  if (confirming && onRewind) {
    return (
      <span className="flex items-center gap-[6px]">
        <span className="font-mono text-[9px] tracking-[0.08em] text-mute uppercase">
          {rewindBeatCount
            ? `Remove ${rewindBeatCount} beat${rewindBeatCount === 1 ? "" : "s"}?`
            : "Rewind here?"}
        </span>
        <button
          type="button"
          onClick={() => {
            setConfirming(false);
            onRewind();
          }}
          className="flex h-[24px] items-center rounded-[3px] bg-accent px-[8px] font-mono text-[9px] tracking-[0.08em] text-[#F6ECDA] uppercase hover:bg-accent-hover"
        >
          Rewind
        </button>
        <button
          type="button"
          onClick={() => setConfirming(false)}
          className="flex h-[24px] items-center rounded-[3px] px-[7px] font-mono text-[9px] tracking-[0.08em] text-mute uppercase hover:bg-hover hover:text-ink"
        >
          Keep
        </button>
      </span>
    );
  }

  return (
    <span className="flex items-center gap-[2px] transition-opacity duration-150 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
      {onEdit ? (
        <button
          type="button"
          onClick={onEdit}
          disabled={disabled}
          aria-label={`Edit ${label}`}
          title="Edit — rewrite this beat's words; nothing after it is lost"
          className="flex h-[44px] w-[44px] items-center justify-center rounded-[3px] text-[13px] text-mute hover:bg-hover hover:text-accent disabled:cursor-not-allowed disabled:opacity-40 sm:h-[24px] sm:w-[24px] sm:text-[11px]"
        >
          <span aria-hidden>✎</span>
        </button>
      ) : null}
      {onReroll ? (
        <>
          <button
            type="button"
            onClick={() => onReroll("beat")}
            disabled={disabled}
            aria-label={`Re-roll ${label}`}
            title="Re-roll — another version of this beat; the current one is kept"
            className="flex h-[44px] w-[44px] items-center justify-center rounded-[3px] text-[13px] text-mute hover:bg-hover hover:text-accent disabled:cursor-not-allowed disabled:opacity-40 sm:h-[24px] sm:w-[24px] sm:text-[11px]"
          >
            <span aria-hidden>⟳</span>
          </button>
          <button
            type="button"
            onClick={() => onReroll("turn")}
            disabled={disabled}
            aria-label={`Re-run the whole turn containing ${label}`}
            title="Re-run the turn — when the beat went wrong because the turn did"
            className="flex h-[44px] w-[44px] items-center justify-center rounded-[3px] text-[13px] text-mute hover:bg-hover hover:text-accent disabled:cursor-not-allowed disabled:opacity-40 sm:h-[24px] sm:w-[24px] sm:text-[11px]"
          >
            <span aria-hidden>⟲</span>
          </button>
        </>
      ) : null}
      {onBranch ? (
        <button
          type="button"
          onClick={onBranch}
          disabled={disabled}
          aria-label={`Branch from ${label}`}
          title="Branch from here — keeps this play-through and starts a new one"
          className="flex h-[44px] w-[44px] items-center justify-center rounded-[3px] text-[13px] text-mute hover:bg-hover hover:text-accent disabled:cursor-not-allowed disabled:opacity-40 sm:h-[24px] sm:w-[24px] sm:text-[11px]"
        >
          <span aria-hidden>⑂</span>
        </button>
      ) : null}
      {onRewind ? (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={disabled}
          aria-label={`Rewind to ${label}`}
          title="Rewind to here — removes this turn and everything after it"
          className="flex h-[44px] w-[44px] items-center justify-center rounded-[3px] text-[13px] text-mute hover:bg-hover hover:text-accent disabled:cursor-not-allowed disabled:opacity-40 sm:h-[24px] sm:w-[24px] sm:text-[11px]"
        >
          <span aria-hidden>↺</span>
        </button>
      ) : null}
    </span>
  );
}
