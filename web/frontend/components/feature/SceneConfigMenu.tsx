"use client";

import { useEffect, useId, useRef, useState } from "react";
import { SceneControlSelect } from "@/components/ui/SceneControlSelect";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { beatsTokensFromTexts, estimateBeatsTokens } from "@/lib/contextBudget";

const MAX_TURN_OPTIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const SUGGESTION_OPTIONS = [0, 1, 2, 3, 4];
// The context-window depth (beats the character conditions on) ranges 5–100.
const BEATS_MIN = 5;
const BEATS_MAX = 100;

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
 * The scene's play-configuration popover — the per-scene controls (Max turns, Suggestions,
 * and the context-window depth "Number of beats", 5–100). Now anchored in the composer's
 * bottom-left controls row (`openUp` flips the popover above the button); when `beatTexts`
 * (the real transcript beats) is passed, the beats readout reflects the ACTUAL recent
 * content rather than a flat average. Native controls + Esc/outside-click close.
 */
export function SceneConfigMenu({
  maxTurns = 5,
  onMaxTurnsChange,
  suggestionsCount = 4,
  onSuggestionsCountChange,
  contextBeats = 14,
  onContextBeatsChange,
  beatTexts,
  openUp = false,
  disabled = false,
}: {
  maxTurns?: number;
  onMaxTurnsChange?: (value: number) => void;
  suggestionsCount?: number;
  onSuggestionsCountChange?: (value: number) => void;
  contextBeats?: number;
  onContextBeatsChange?: (value: number) => void;
  /** The real transcript beats (one string each) — makes the readout content-real. */
  beatTexts?: string[];
  /** Open the popover upward (for the bottom-of-screen composer). */
  openUp?: boolean;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const beatsId = useId();

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

  // Content-real when the transcript is available; the flat average is the fallback.
  const beatsTokens = beatTexts
    ? beatsTokensFromTexts(beatTexts, contextBeats)
    : estimateBeatsTokens(contextBeats);
  const beatsLabel = beatTexts ? "tokens (recent beats)" : "tokens of context";

  return (
    <div ref={ref} className="relative flex-none">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label="Scene configuration"
        className="flex flex-none items-center gap-[6px] rounded-[2px] border border-field-bd px-[10px] py-[6px] font-mono text-[9px] tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent aria-expanded:border-accent aria-expanded:text-accent"
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
          className={`absolute left-0 z-40 flex w-[264px] flex-col gap-[13px] rounded-[4px] border border-cardbd bg-card p-[14px] shadow-[0_8px_24px_rgba(20,14,6,.18)] focus:outline-none ${
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

          <div className="flex flex-col gap-[5px]">
            <div className="flex items-baseline justify-between">
              <label
                htmlFor={beatsId}
                className="font-mono text-[9px] tracking-[0.12em] text-mute2 uppercase"
              >
                Number of beats
              </label>
              <span className="font-mono text-[12px] text-ink tabular-nums">{contextBeats}</span>
            </div>
            <input
              id={beatsId}
              type="range"
              min={BEATS_MIN}
              max={BEATS_MAX}
              step={1}
              value={contextBeats}
              onChange={(e) => onContextBeatsChange?.(Number(e.target.value))}
              disabled={disabled || !onContextBeatsChange}
              aria-label="Number of beats"
              className="w-full accent-accent disabled:opacity-60"
            />
            <span className="font-mono text-[10px] tracking-[0.04em] text-ink-soft">
              ≈ {beatsTokens.toLocaleString()} {beatsLabel}
            </span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
