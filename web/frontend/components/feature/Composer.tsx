import type { RefObject } from "react";
import { SceneControlSelect } from "@/components/ui/SceneControlSelect";

// Selectable ranges for the two per-scene controls.
const MAX_TURN_OPTIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const SUGGESTION_OPTIONS = [0, 1, 2, 3, 4];

/** Bottom composer: per-scene controls (turn limit + suggestion count), message input, send. */
export function Composer({
  value,
  onChange,
  onSend,
  disabled = false,
  maxTurns = 5,
  onMaxTurnsChange,
  suggestionsCount = 4,
  onSuggestionsCountChange,
  inputRef,
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  /** While a turn is streaming, lock input + send. */
  disabled?: boolean;
  /** Hard ceiling on character replies per player message (persisted per scene). */
  maxTurns?: number;
  onMaxTurnsChange?: (value: number) => void;
  /** How many follow-up suggestions to offer after a turn (0–4; persisted per scene). */
  suggestionsCount?: number;
  onSuggestionsCountChange?: (value: number) => void;
  /** Lets the parent move focus here after a suggestion is written into the box (request #2). */
  inputRef?: RefObject<HTMLInputElement | null>;
}) {
  return (
    <div className="velora-header flex-none border-t border-hair-strong p-[13px_16px] sm:p-[13px_30px]">
      <div className="mx-auto flex max-w-[720px] flex-wrap items-end gap-[10px]">
        <SceneControlSelect
          label="Max turns"
          value={maxTurns}
          options={MAX_TURN_OPTIONS}
          onChange={(v) => onMaxTurnsChange?.(v)}
          disabled={!onMaxTurnsChange}
        />
        <SceneControlSelect
          label="Suggestions"
          value={suggestionsCount}
          options={SUGGESTION_OPTIONS}
          onChange={(v) => onSuggestionsCountChange?.(v)}
          disabled={!onSuggestionsCountChange}
        />
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !disabled) onSend();
          }}
          disabled={disabled}
          aria-label="Your message"
          placeholder={disabled ? "The scene responds…" : "Speak, or describe what you do…"}
          className="min-w-[160px] flex-1 basis-[200px] rounded-[3px] border border-field-bd bg-field p-[10px_14px] font-body text-[15px] text-ink focus:border-accent focus:outline-none disabled:opacity-60"
        />
        <button
          type="button"
          onClick={onSend}
          disabled={disabled}
          className="flex-none rounded-[3px] bg-accent p-[11px_20px] font-mono text-[11px] tracking-[0.1em] text-[#F6ECDA] uppercase hover:brightness-110 disabled:opacity-50 disabled:hover:brightness-100"
        >
          Send ▸
        </button>
      </div>
    </div>
  );
}
