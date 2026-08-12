"use client";

import type { MentionOption } from "@/features/story-player/mentions";

/**
 * The `@` file-tagging completion list, anchored above the composer.
 *
 * Presentational only: the composer owns which option is highlighted and every keystroke,
 * because Enter has to select here *instead of* sending the turn — the two behaviours
 * cannot be decided in two places. Roles are `listbox`/`option` (not `menu`/`menuitem`)
 * because this is a completion list attached to a textarea, so focus stays in the
 * textarea and the active row is announced via `aria-activedescendant`.
 *
 * Surface, placement and row styling reuse `mytheca-menu` and the `PovSelect` popover
 * conventions, so the composer gains no new visual language.
 */
export function MentionMenu({
  id,
  options,
  activeIndex,
  optionId,
  onSelect,
}: {
  id: string;
  options: MentionOption[];
  activeIndex: number;
  /** Builds the per-row DOM id the textarea's `aria-activedescendant` points at. */
  optionId: (index: number) => string;
  onSelect: (option: MentionOption) => void;
}) {
  if (options.length === 0) return null;

  return (
    <div
      id={id}
      role="listbox"
      aria-label="Context files"
      className="absolute bottom-full left-0 z-40 mb-[6px] flex max-h-[280px] w-full max-w-[320px] flex-col gap-[2px] overflow-auto mytheca-menu p-[6px]"
    >
      {options.map((opt, i) => {
        const active = i === activeIndex;
        return (
          <button
            key={opt.id}
            id={optionId(i)}
            type="button"
            role="option"
            aria-selected={active}
            tabIndex={-1}
            // The textarea keeps focus, so the pointer must not steal it on press.
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => onSelect(opt)}
            className={`flex w-full items-center gap-[8px] rounded-[3px] px-[8px] py-[6px] text-left text-ink hover:bg-hover focus:outline-none ${
              active ? "bg-hover text-accent" : ""
            }`}
          >
            <span aria-hidden className="text-[12px] text-mute">
              ⎙
            </span>
            <span className="min-w-0 flex-1 truncate font-display text-[13px] font-semibold">
              {opt.name}
            </span>
            {typeof opt.charCount === "number" ? (
              <span className="flex-none text-[11px] text-mute">{opt.charCount} ch</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
