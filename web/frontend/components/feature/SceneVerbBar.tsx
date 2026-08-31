"use client";

import { useRef, useState } from "react";
import {
  VERB_GROUPS,
  VERB_GROUP_LABELS,
  type SceneVerb,
  type VerbGroup,
} from "@/lib/sceneVerbs";

/**
 * The direction verbs, as a grouped toolbar on the direction row.
 *
 * **Grouped, not a flat row.** Four labelled groups (Pace · Tone · Event · Exit) so the bar
 * reads as a set of choices about *different* things rather than a wall of buttons. That is
 * the fix for "users don't even look at it half the time": a flat row makes the reader scan
 * every label to find the one axis they care about.
 *
 * **One tab stop, arrow keys inside** (roving tabindex, the WAI-ARIA toolbar pattern). A
 * toolbar of fifteen chips that each take a tab stop would put fifteen presses between the
 * composer and the Send button, which is worse for a keyboard user than not having the bar.
 *
 * Scrolls horizontally inside its own container, so it can never widen the page at 320px.
 */
export function SceneVerbBar({
  verbs,
  onVerb,
  onExpandCast,
  disabled = false,
}: {
  verbs: SceneVerb[];
  /** Insert this phrasing into the direction target. */
  onVerb: (text: string) => void;
  /** A verb that expands rather than inserts — today only "Someone arrives". */
  onExpandCast?: () => void;
  disabled?: boolean;
}) {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  // Gates open and close between turns (the Exit verbs appear, "Someone arrives" vanishes),
  // so the stored index can fall off the end of a shorter list. Clamped during render rather
  // than corrected in an effect: an effect would render one frame with an out-of-range
  // roving index, and setting state from one cascades a second render for nothing.
  const index = active < verbs.length ? active : 0;

  if (!verbs.length) return null;

  const focusAt = (i: number) => {
    setActive(i);
    refs.current[i]?.focus();
  };

  function onKeyDown(e: React.KeyboardEvent<HTMLButtonElement>, index: number) {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      focusAt((index + 1) % verbs.length);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      focusAt((index - 1 + verbs.length) % verbs.length);
    } else if (e.key === "Home") {
      e.preventDefault();
      focusAt(0);
    } else if (e.key === "End") {
      e.preventDefault();
      focusAt(verbs.length - 1);
    }
  }

  // The flat position each verb has in `verbs`, so drawing by group never renumbers the
  // roving order — the toolbar is one list to the keyboard however it is laid out.
  const positionOf = new Map(verbs.map((v, i) => [v.id, i]));

  return (
    <div
      role="toolbar"
      aria-label="Direction"
      className="-mx-3xs flex max-w-full items-center gap-sm overflow-x-auto px-3xs py-3xs"
    >
      {VERB_GROUPS.map((group: VerbGroup) => {
        const rows = verbs.filter((v) => v.group === group);
        if (!rows.length) return null;
        return (
          <div
            key={group}
            role="group"
            aria-label={VERB_GROUP_LABELS[group]}
            className="flex flex-none items-center gap-2xs"
          >
            <span
              aria-hidden
              className="flex-none font-mono text-eyebrow tracking-[0.12em] text-mute2 uppercase"
            >
              {VERB_GROUP_LABELS[group]}
            </span>
            {rows.map((verb) => {
              const position = positionOf.get(verb.id) ?? 0;
              return (
                <button
                  key={verb.id}
                  ref={(el) => {
                    refs.current[position] = el;
                  }}
                  type="button"
                  // Roving: exactly one chip is tabbable at a time.
                  tabIndex={position === index ? 0 : -1}
                  disabled={disabled}
                  onFocus={() => setActive(position)}
                  onKeyDown={(e) => onKeyDown(e, position)}
                  onClick={() =>
                    verb.expands === "cast" ? onExpandCast?.() : onVerb(verb.text)
                  }
                  className="min-h-[24px] flex-none rounded-sm border border-field-bd px-xs py-3xs font-mono text-eyebrow tracking-[0.06em] whitespace-nowrap text-mute uppercase hover:bg-hover hover:text-ink disabled:opacity-40 disabled:hover:bg-transparent"
                >
                  {verb.label}
                </button>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
