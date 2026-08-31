"use client";

import { useRef, useState } from "react";

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
 *
 * **One tab stop per beat, not five.** The cluster is a `role="toolbar"` with a roving
 * tabindex (the idiom `LibraryTabs` already uses): Tab enters it once and leaves it once,
 * and Arrow keys / Home / End move between the controls inside. Measured before this: a
 * twelve-beat transcript put **57** controls in the tab order, so reaching the composer by
 * keyboard meant passing every edit, re-roll and rewind button in the scene.
 */
export function BeatControls({
  onEdit,
  onReroll,
  onBranch,
  onRewind,
  rewindBeatCount,
  rewindEmptiesScene = false,
  disabled = false,
  label = "this beat",
}: {
  /**
   * Rewrite this beat's prose. Passed only for a beat the **player wrote** — their own
   * line, or a POV line they authored in a character's name. Omitted for the cast's prose
   * and the narration, whose answer to "I don't like that line" is *Re-roll*; and omitted
   * for a beat with no prose at all (a stat change, a set of choices).
   */
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
  /**
   * True when this beat sits in the play-through's **first** turn, so rewinding to it takes
   * the whole scene rather than trimming a tail.
   *
   * A rewind removes the containing turn *and everything after it*, which from turn one is
   * everything — and the confirmation used to say "Remove 5 beats?" in exactly the words it
   * uses to trim one exchange off the end. Reported from a live scene as "Rewind to Here
   * deletes the whole thread". Nothing is actually lost (the pre-cut history forks to a tray
   * row and the notice offers Undo); what was missing was being told.
   */
  rewindEmptiesScene?: boolean;
  /** True while a turn is streaming: the record must not be edited mid-sentence. */
  disabled?: boolean;
  /** What this beat is, for the controls' accessible names. */
  label?: string;
}) {
  const [confirming, setConfirming] = useState(false);
  /** Which control in the cluster currently holds the single tab stop. */
  const [active, setActive] = useState(0);
  const barRef = useRef<HTMLSpanElement>(null);

  /**
   * Arrow / Home / End move within the cluster; everything else (Tab included) is left to
   * the browser, which is what makes this one stop rather than a keyboard trap.
   */
  const onKeyDown = (event: React.KeyboardEvent<HTMLSpanElement>) => {
    const keys = ["ArrowRight", "ArrowLeft", "Home", "End"];
    if (!keys.includes(event.key)) return;
    const items = [...(barRef.current?.querySelectorAll<HTMLButtonElement>("button") ?? [])];
    if (items.length === 0) return;
    event.preventDefault();
    const current = items.findIndex((el) => el === document.activeElement);
    const from = current === -1 ? active : current;
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? items.length - 1
          : (from + (event.key === "ArrowRight" ? 1 : -1) + items.length) % items.length;
    setActive(next);
    items[next]?.focus();
  };

  if (!onEdit && !onReroll && !onBranch && !onRewind) return null;

  if (confirming && onRewind) {
    return (
      <span className="flex items-center gap-xs">
        <span className="font-mono text-eyebrow tracking-[0.08em] text-mute uppercase">
          {rewindEmptiesScene && rewindBeatCount
            ? `Empty the scene — all ${rewindBeatCount} beats?`
            : rewindBeatCount
              ? `Remove ${rewindBeatCount} beat${rewindBeatCount === 1 ? "" : "s"}?`
              : "Rewind here?"}
        </span>
        <button
          type="button"
          onClick={() => {
            setConfirming(false);
            onRewind();
          }}
          className="flex h-[24px] items-center rounded-xs bg-accent px-sm font-mono text-eyebrow tracking-[0.08em] text-[#F6ECDA] uppercase hover:bg-accent-hover"
        >
          Rewind
        </button>
        <button
          type="button"
          onClick={() => setConfirming(false)}
          className="flex h-[24px] items-center rounded-xs px-xs font-mono text-eyebrow tracking-[0.08em] text-mute uppercase hover:bg-hover hover:text-ink"
        >
          Keep
        </button>
      </span>
    );
  }

  /**
   * The controls that will actually be rendered, in order.
   *
   * Built as a list rather than five conditional blocks because the roving tabindex has to
   * index the RENDERED controls. With hardcoded positions, a beat that has no `onEdit` — a
   * stat change, a set of choices — would leave the tab stop assigned to a control that does
   * not exist, and the whole cluster would drop out of the tab order.
   */
  const controls: { key: string; label: string; title: string; glyph: string; onClick: () => void }[] = [
    ...(onEdit
      ? [{
          key: "edit",
          label: `Edit ${label}`,
          title: "Edit — rewrite this beat's words; nothing after it is lost",
          glyph: "✎",
          onClick: onEdit,
        }]
      : []),
    ...(onReroll
      ? [
          {
            key: "reroll-beat",
            label: `Re-roll ${label}`,
            title: "Re-roll — another version of this beat; the current one is kept",
            glyph: "⟳",
            onClick: () => onReroll("beat"),
          },
          {
            key: "reroll-turn",
            label: `Re-run the whole turn containing ${label}`,
            title: "Re-run the turn — when the beat went wrong because the turn did",
            glyph: "⟲",
            onClick: () => onReroll("turn"),
          },
        ]
      : []),
    ...(onBranch
      ? [{
          key: "branch",
          label: `Branch from ${label}`,
          title: "Branch from here — keeps this play-through and starts a new one",
          glyph: "⑂",
          onClick: onBranch,
        }]
      : []),
    ...(onRewind
      ? [{
          key: "rewind",
          label: `Rewind to ${label}`,
          title: rewindEmptiesScene
            ? "Rewind to here — this is the first turn, so it empties the scene (undoable)"
            : "Rewind to here — removes this turn and everything after it",
          glyph: "↺",
          onClick: () => setConfirming(true),
        }]
      : []),
  ];

  // Clamped, so a cluster that loses a control mid-life still has exactly one tab stop.
  const activeIndex = Math.min(active, controls.length - 1);

  return (
    <span
      ref={barRef}
      role="toolbar"
      aria-label={`Actions for ${label}`}
      aria-orientation="horizontal"
      onKeyDown={onKeyDown}
      className="flex items-center gap-3xs transition-opacity duration-150 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
    >
      {controls.map((control, i) => (
        <button
          key={control.key}
          type="button"
          onClick={control.onClick}
          disabled={disabled}
          aria-label={control.label}
          title={control.title}
          tabIndex={i === activeIndex ? 0 : -1}
          onFocus={() => setActive(i)}
          className="flex h-[44px] w-[44px] items-center justify-center rounded-xs text-label text-mute hover:bg-hover hover:text-accent-ink disabled:cursor-not-allowed disabled:opacity-40 sm:h-[24px] sm:w-[24px] sm:text-eyebrow"
        >
          <span aria-hidden>{control.glyph}</span>
        </button>
      ))}
    </span>
  );
}
