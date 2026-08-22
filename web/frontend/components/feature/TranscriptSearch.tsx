"use client";

import { useEffect, useRef } from "react";
import { CloseButton } from "@/components/ui/CloseButton";

/**
 * The find bar for a long scene.
 *
 * Two decisions worth stating.
 *
 * **The count is announced, not just drawn.** "3 of 17" in a live region is the whole
 * feedback loop of a search: without it, a screen-reader user pressing next has no way to
 * know whether anything moved.
 *
 * **`Cmd/Ctrl+F` is only borrowed when the composer is not focused.** Someone writing a line
 * who reaches for find-in-page means the browser's, and stealing it there would be the same
 * failure as a shortcut eating a keystroke. The caller owns that check.
 */
export function TranscriptSearch({
  query,
  onQueryChange,
  current,
  total,
  onStep,
  onClose,
}: {
  query: string;
  onQueryChange: (next: string) => void;
  /** 0-based index of the highlighted match. */
  current: number;
  total: number;
  onStep: (delta: 1 | -1) => void;
  onClose: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const status = !query.trim()
    ? "Type to search this scene"
    : total === 0
      ? "No matches"
      : `${current + 1} of ${total}`;

  return (
    <div
      role="search"
      aria-label="Search this scene"
      className="mx-auto flex w-full max-w-[720px] flex-none items-center gap-[8px] rounded-[10px] border border-field-bd bg-field px-[10px] py-[7px]"
    >
      <input
        ref={inputRef}
        type="search"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            onStep(e.shiftKey ? -1 : 1);
          } else if (e.key === "Escape") {
            e.preventDefault();
            onClose();
          }
        }}
        placeholder="Find in this scene…"
        aria-label="Find in this scene"
        className="composer-input min-w-0 flex-1 bg-transparent font-body text-[13px] text-ink placeholder:text-mute2 focus:outline-none"
      />
      {/* The feedback loop of a search. Polite, so it does not interrupt the transcript. */}
      <span
        role="status"
        aria-live="polite"
        className="flex-none font-mono text-[10px] tracking-[0.06em] whitespace-nowrap text-mute2 tabular-nums"
      >
        {status}
      </span>
      <button
        type="button"
        onClick={() => onStep(-1)}
        disabled={total === 0}
        aria-label="Previous match"
        className="flex h-[24px] w-[24px] flex-none items-center justify-center rounded-[4px] text-[12px] text-mute hover:bg-hover hover:text-ink disabled:opacity-40 disabled:hover:bg-transparent"
      >
        ↑
      </button>
      <button
        type="button"
        onClick={() => onStep(1)}
        disabled={total === 0}
        aria-label="Next match"
        className="flex h-[24px] w-[24px] flex-none items-center justify-center rounded-[4px] text-[12px] text-mute hover:bg-hover hover:text-ink disabled:opacity-40 disabled:hover:bg-transparent"
      >
        ↓
      </button>
      <CloseButton onClose={onClose} className="relative" />
    </div>
  );
}
