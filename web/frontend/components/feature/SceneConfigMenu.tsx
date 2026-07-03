"use client";

import { useEffect, useId, useRef, useState } from "react";
import { SceneControlSelect } from "@/components/ui/SceneControlSelect";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { estimateBeatsTokens } from "@/lib/contextBudget";

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
 * The scene's play-configuration popover, anchored left of the composer input. Holds the
 * per-scene controls — Max turns, Suggestions, and the context-window depth (Number of beats,
 * 5–100) with a live approximate token estimate. Native controls + Esc/outside-click close.
 */
export function SceneConfigMenu({
  maxTurns = 5,
  onMaxTurnsChange,
  suggestionsCount = 4,
  onSuggestionsCountChange,
  contextBeats = 14,
  onContextBeatsChange,
  disabled = false,
}: {
  maxTurns?: number;
  onMaxTurnsChange?: (value: number) => void;
  suggestionsCount?: number;
  onSuggestionsCountChange?: (value: number) => void;
  contextBeats?: number;
  onContextBeatsChange?: (value: number) => void;
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

  const beatsTokens = estimateBeatsTokens(contextBeats);

  return (
    <div ref={ref} className="relative flex-none">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label="Scene configuration"
        className="flex items-center gap-[6px] rounded-[3px] border border-field-bd bg-field p-[9px_11px] font-mono text-[11px] tracking-[0.1em] text-ink uppercase hover:border-accent focus:border-accent focus:outline-none"
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
          className="absolute bottom-full left-0 z-20 mb-[8px] flex w-[264px] flex-col gap-[13px] rounded-[4px] border border-cardbd bg-card p-[14px] shadow-[0_8px_24px_rgba(20,14,6,.18)] focus:outline-none"
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
              ≈ {beatsTokens.toLocaleString()} tokens of context
            </span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
