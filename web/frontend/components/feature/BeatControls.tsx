"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { useMediaQuery } from "@/hooks/use-media-query";

/** One thing the player can do to a beat that has already landed. */
type Control = {
  key: string;
  /** The accessible name, and the row's words in the narrow menu. */
  label: string;
  /** Short imperative words for the menu row — the tooltip's clause is too long to read. */
  short: string;
  title: string;
  icon: IconName;
  onClick: () => void;
};

/**
 * The per-beat control cluster: what the player can do to a beat that has already landed.
 *
 * It renders two ways, and they are not two components:
 *
 * - **Wide** — a `role="toolbar"` of icon buttons, quiet until the beat is hovered or
 *   contains focus. Visibility is `opacity-0`, never `display: none`: a hidden control is
 *   out of the tab order, which would make every one of these mouse-only.
 * - **Narrow** — a single `⋯` trigger opening a menu of the same actions, each with its
 *   icon *and its words*. Five 44px targets is 220px of chrome on every beat of the
 *   transcript, on the narrowest screen in the app, and on a phone there is no hover to
 *   hide it behind. Both renderings are built from the same `controls` list, so an action
 *   added to one cannot go missing from the other.
 *
 * The glyphs are the shared icon set, not text characters. `✎ ⟳ ⟲ ⑂ ↺` inherited the font
 * stack — different per platform, sized by the type scale rather than by the control — and
 * asked the player to tell `⟳` from `⟲` at 12px, which is the same arrow with the head at
 * the other end.
 *
 * Rewind confirms in place, because it removes content. Branch does not, because it removes
 * nothing — that asymmetry is the point: the non-destructive way to explore is the one that
 * costs a single click.
 *
 * **One tab stop per beat, not five.** The wide cluster is a `role="toolbar"` with a roving
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
  const [menuOpen, setMenuOpen] = useState(false);
  const barRef = useRef<HTMLSpanElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  /**
   * The Tailwind `sm` breakpoint, inverted.
   *
   * `false` on the server, and wherever `matchMedia` is absent — deliberately the WIDE
   * rendering, because that one is the superset: every action present, named and in the tab
   * order. A viewport we do not yet know about should get the whole cluster, not a menu
   * standing in front of it.
   */
  const narrow = useMediaQuery("(max-width: 639px)");

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

  // Outside-click and Escape close the narrow menu. Escape returns focus to the trigger,
  // because dismissing a menu should not drop the player at the top of the document.
  useEffect(() => {
    if (!menuOpen) return;
    function onDocMouseDown(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
        setConfirming(false);
      }
    }
    function onDocKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setMenuOpen(false);
      setConfirming(false);
      triggerRef.current?.focus();
    }
    document.addEventListener("mousedown", onDocMouseDown);
    document.addEventListener("keydown", onDocKeyDown);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      document.removeEventListener("keydown", onDocKeyDown);
    };
  }, [menuOpen]);

  /**
   * The controls that will actually be rendered, in order.
   *
   * Built as a list rather than five conditional blocks because the roving tabindex has to
   * index the RENDERED controls. With hardcoded positions, a beat that has no `onEdit` — a
   * stat change, a set of choices — would leave the tab stop assigned to a control that does
   * not exist, and the whole cluster would drop out of the tab order. The narrow menu reads
   * the same list, which is what keeps the two renderings from drifting apart.
   */
  const controls: Control[] = [
    ...(onEdit
      ? [{
          key: "edit",
          label: `Edit ${label}`,
          short: "Edit",
          title: "Edit — rewrite this beat's words; nothing after it is lost",
          icon: "pencil" as const,
          onClick: onEdit,
        }]
      : []),
    ...(onReroll
      ? [
          {
            key: "reroll-beat",
            label: `Re-roll ${label}`,
            short: "Re-roll this beat",
            title: "Re-roll — another version of this beat; the current one is kept",
            icon: "reroll" as const,
            onClick: () => onReroll("beat"),
          },
          {
            key: "reroll-turn",
            label: `Re-run the whole turn containing ${label}`,
            short: "Re-run the whole turn",
            title: "Re-run the turn — when the beat went wrong because the turn did",
            icon: "rerun" as const,
            onClick: () => onReroll("turn"),
          },
        ]
      : []),
    ...(onBranch
      ? [{
          key: "branch",
          label: `Branch from ${label}`,
          short: "Branch from here",
          title: "Branch from here — keeps this play-through and starts a new one",
          icon: "branch" as const,
          onClick: onBranch,
        }]
      : []),
    ...(onRewind
      ? [{
          key: "rewind",
          label: `Rewind to ${label}`,
          short: rewindEmptiesScene ? "Rewind — empties the scene" : "Rewind to here",
          title: rewindEmptiesScene
            ? "Rewind to here — this is the first turn, so it empties the scene (undoable)"
            : "Rewind to here — removes this turn and everything after it",
          icon: "rewind" as const,
          onClick: () => setConfirming(true),
        }]
      : []),
  ];

  if (controls.length === 0) return null;

  /** The question the rewind confirmation asks — identical in both renderings. */
  const rewindQuestion =
    rewindEmptiesScene && rewindBeatCount
      ? `Empty the scene — all ${rewindBeatCount} beats?`
      : rewindBeatCount
        ? `Remove ${rewindBeatCount} beat${rewindBeatCount === 1 ? "" : "s"}?`
        : "Rewind here?";

  const confirmButtons = onRewind ? (
    <>
      <button
        type="button"
        onClick={() => {
          setConfirming(false);
          setMenuOpen(false);
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
    </>
  ) : null;

  // ---- narrow: one trigger, one menu ----
  if (narrow) {
    return (
      <div ref={menuRef} className="relative flex items-center">
        <button
          ref={triggerRef}
          type="button"
          onClick={() => {
            setMenuOpen((v) => !v);
            setConfirming(false);
          }}
          disabled={disabled}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          aria-controls={menuOpen ? menuId : undefined}
          aria-label={`Actions for ${label}`}
          className="flex h-[44px] w-[44px] items-center justify-center rounded-xs text-mute hover:bg-hover hover:text-accent-ink disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Icon name="more" size={18} filled strokeWidth={0} />
        </button>
        {menuOpen ? (
          <div
            id={menuId}
            role="menu"
            aria-label={`Actions for ${label}`}
            // Opens UPWARD and pinned to this beat's right edge: the bar already sits at
            // the foot of the beat, so a downward panel would cover the beat that follows —
            // the one the player is most likely reading.
            className="mytheca-menu mytheca-menu-up absolute right-0 bottom-full z-40 mb-3xs flex w-[230px] flex-col p-3xs"
          >
            {confirming && onRewind ? (
              <div className="flex flex-col gap-2xs p-xs">
                <span className="font-mono text-eyebrow tracking-[0.08em] text-mute uppercase">
                  {rewindQuestion}
                </span>
                <span className="flex items-center gap-xs">{confirmButtons}</span>
              </div>
            ) : (
              controls.map((control) => (
                <button
                  key={control.key}
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    // Rewind swaps the menu's body for its confirmation rather than closing
                    // it: the question has to land where the finger already is.
                    if (control.key !== "rewind") setMenuOpen(false);
                    control.onClick();
                  }}
                  disabled={disabled}
                  className="flex min-h-[44px] items-center gap-sm rounded-xs px-sm text-left text-body-sm text-ink hover:bg-hover hover:text-accent-ink disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <Icon name={control.icon} size={16} className="text-mute" />
                  <span className="min-w-0 flex-1 truncate">{control.short}</span>
                </button>
              ))
            )}
          </div>
        ) : null}
      </div>
    );
  }

  // ---- wide: the toolbar ----
  if (confirming && onRewind) {
    return (
      <span className="flex items-center gap-xs">
        <span className="font-mono text-eyebrow tracking-[0.08em] text-mute uppercase">
          {rewindQuestion}
        </span>
        {confirmButtons}
      </span>
    );
  }

  // Clamped, so a cluster that loses a control mid-life still has exactly one tab stop.
  const activeIndex = Math.min(active, controls.length - 1);

  return (
    <span
      ref={barRef}
      role="toolbar"
      aria-label={`Actions for ${label}`}
      aria-orientation="horizontal"
      onKeyDown={onKeyDown}
      className="flex items-center gap-3xs"
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
          className="flex h-[26px] w-[26px] items-center justify-center rounded-xs text-mute hover:bg-hover hover:text-accent-ink disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Icon name={control.icon} size={14} />
        </button>
      ))}
    </span>
  );
}
