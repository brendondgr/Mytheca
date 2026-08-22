"use client";

import { useEffect, useId, useRef, useState } from "react";
import { SceneControlSelect } from "@/components/ui/SceneControlSelect";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { BEAT_LENGTHS, BEAT_LENGTH_LABELS, type BeatLength } from "@/lib/types";

const MAX_TURN_OPTIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const SUGGESTION_OPTIONS = [0, 1, 2, 3, 4];
// Value + rendered text, built from the contract in lib/types so the tiers cannot drift
// from the backend `Literal` they mirror.
const BEAT_LENGTH_OPTIONS = BEAT_LENGTHS.map((value) => ({
  value,
  label: BEAT_LENGTH_LABELS[value],
}));

function GearIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
    </svg>
  );
}

/**
 * The scene's play-configuration popover — Max turns, Suggestions, Beat length.
 *
 * **"Number of beats" was deleted, not hidden.** It asked the player to pick a
 * context-window depth, which is a question only the app can answer: the right depth is
 * whatever the model can actually hold, and the app knows the model's window while the
 * player does not. The window now fits itself each turn
 * (`services/context_budget` + the scene's `contextPolicy`), and what the scene reached is
 * *reported* in the Inspector rather than *configured* here.
 *
 * Anchored in the composer's bottom-left controls row (`openUp` flips the popover above the
 * button). Native controls + Esc/outside-click close.
 */
export function SceneConfigMenu({
  maxTurns = 5,
  onMaxTurnsChange,
  suggestionsCount = 4,
  onSuggestionsCountChange,
  beatLength = "medium",
  onBeatLengthChange,
  openUp = false,
  disabled = false,
}: {
  maxTurns?: number;
  onMaxTurnsChange?: (value: number) => void;
  suggestionsCount?: number;
  onSuggestionsCountChange?: (value: number) => void;
  /** How much a character says in one beat — short 1–2 ¶, medium 2–4 ¶, long 5–6 ¶. */
  beatLength?: BeatLength;
  onBeatLengthChange?: (value: BeatLength) => void;
  /** Open the popover upward (for the bottom-of-screen composer). */
  openUp?: boolean;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  // Close on outside pointerdown or Escape; move focus into the panel when it opens.
  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative flex-none">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label="Scene configuration"
        className="flex flex-none items-center gap-[5px] rounded-[8px] border border-field-bd px-[9px] py-[5px] font-mono text-[9px] tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent aria-expanded:border-accent aria-expanded:text-accent"
      >
        <GearIcon />
        Config
      </button>

      {open ? (
        <div
          ref={panelRef}
          id={panelId}
          role="dialog"
          aria-label="Scene configuration"
          tabIndex={-1}
          className={`absolute left-0 z-40 flex w-[264px] flex-col gap-[13px] mytheca-menu p-[14px] focus:outline-none ${
            openUp ? "bottom-[38px]" : "top-[38px]"
          }`}
        >
          <Eyebrow tracking="0.16em" color="var(--accent)">
            Scene configuration
          </Eyebrow>

          <SceneControlSelect
            label="Max turns"
            value={maxTurns}
            options={MAX_TURN_OPTIONS}
            onChange={(v) => onMaxTurnsChange?.(v)}
            disabled={disabled || !onMaxTurnsChange}
            className="w-full [&_select]:w-full"
          />

          <SceneControlSelect
            label="Suggestions"
            value={suggestionsCount}
            options={SUGGESTION_OPTIONS}
            onChange={(v) => onSuggestionsCountChange?.(v)}
            disabled={disabled || !onSuggestionsCountChange}
            className="w-full [&_select]:w-full"
          />

          <SceneControlSelect
            label="Beat length"
            value={beatLength}
            options={BEAT_LENGTH_OPTIONS}
            onChange={(v) => onBeatLengthChange?.(v)}
            disabled={disabled || !onBeatLengthChange}
            className="w-full [&_select]:w-full"
          />
        </div>
      ) : null}
    </div>
  );
}
