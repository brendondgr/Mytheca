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
  onBranch,
  onRewind,
  rewindBeatCount,
  disabled = false,
  label = "this beat",
}: {
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

  if (!onBranch && !onRewind) return null;

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
    <span className="flex items-center gap-[2px] opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
      {onBranch ? (
        <button
          type="button"
          onClick={onBranch}
          disabled={disabled}
          aria-label={`Branch from ${label}`}
          title="Branch from here — keeps this play-through and starts a new one"
          className="flex h-[24px] w-[24px] items-center justify-center rounded-[3px] text-[11px] text-mute hover:bg-hover hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
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
          className="flex h-[24px] w-[24px] items-center justify-center rounded-[3px] text-[11px] text-mute hover:bg-hover hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
        >
          <span aria-hidden>↺</span>
        </button>
      ) : null}
    </span>
  );
}
