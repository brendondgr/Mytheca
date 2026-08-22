"use client";

import { Monogram } from "@/components/ui/Monogram";
import type { MentionOption } from "@/features/story-player/mentions";
import { mediaUrl } from "@/lib/api";

/**
 * The `@` completion list, anchored above the composer.
 *
 * Presentational only: the composer owns which option is highlighted and every keystroke,
 * because Enter has to select here *instead of* sending the turn — the two behaviours
 * cannot be decided in two places. Roles are `listbox`/`option` (not `menu`/`menuitem`)
 * because this is a completion list attached to a textarea, so focus stays in the
 * textarea and the active row is announced via `aria-activedescendant`.
 *
 * It offers **two kinds** in one namespace — the present cast and the storyline's context
 * files — because the player types one `@` and does not think about which subsystem a name
 * belongs to. They are visually and programmatically separated into two labelled
 * `role="group"` sections, since what they *do* is entirely different: a character aims the
 * line, a file grounds it. The roving `activeIndex` addresses a **flat** index across both
 * groups, so the composer's Arrow/Enter/Tab/Escape handling is unchanged.
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

  // The flat order the composer's keyboard navigation walks. Rendering groups must not
  // renumber the rows, so each row carries the index it has in `options` itself.
  const cast = options
    .map((opt, i) => ({ opt, i }))
    .filter(({ opt }) => opt.kind === "cast");
  const docs = options
    .map((opt, i) => ({ opt, i }))
    .filter(({ opt }) => opt.kind !== "cast");

  const row = ({ opt, i }: { opt: MentionOption; i: number }) => {
    const active = i === activeIndex;
    const isCast = opt.kind === "cast";
    return (
      <button
        key={opt.id}
        id={optionId(i)}
        type="button"
        role="option"
        aria-selected={active}
        // Names alone read identically for a character and a file of the same name; the
        // kind is what tells them apart, so it is spoken, not only drawn.
        aria-label={isCast ? `${opt.name}, character` : `${opt.name}, context file`}
        tabIndex={-1}
        // The textarea keeps focus, so the pointer must not steal it on press.
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => onSelect(opt)}
        // The active row is marked by the composer's 2px inset accent bar rather than a
        // text colour: `bg-hover` is dark enough that the muted secondary text would
        // fall below AA on it, so both labels stay `text-ink` and hierarchy comes from
        // size and weight instead.
        className={`flex w-full items-center gap-[8px] rounded-[3px] border-l-2 px-[8px] py-[6px] text-left text-ink hover:bg-hover focus:outline-none ${
          active ? "border-accent bg-hover" : "border-transparent"
        }`}
      >
        {isCast ? (
          <Monogram
            mono={opt.mono ?? opt.name.slice(0, 1).toUpperCase()}
            color={opt.color ?? "#8E2B1C"}
            size={18}
            ring={1}
            fontSize={9}
            src={opt.portrait ? mediaUrl(opt.portrait) : null}
          />
        ) : (
          <span aria-hidden className="text-[12px]">
            ⎙
          </span>
        )}
        <span className="min-w-0 flex-1 truncate font-display text-[13px] font-semibold">
          {opt.name}
        </span>
        {!isCast && typeof opt.charCount === "number" ? (
          <span className="flex-none text-[11px]">{opt.charCount} ch</span>
        ) : null}
      </button>
    );
  };

  const heading = (text: string) => (
    <span
      aria-hidden
      className="block px-[8px] pt-[4px] pb-[2px] font-mono text-[9px] tracking-[0.14em] text-mute2 uppercase"
    >
      {text}
    </span>
  );

  return (
    <div
      id={id}
      role="listbox"
      aria-label="Cast and context files"
      className="mytheca-menu absolute bottom-full left-0 z-40 mb-[6px] flex max-h-[280px] w-full max-w-[320px] flex-col gap-[2px] overflow-auto p-[6px]"
    >
      {cast.length ? (
        <div role="group" aria-label="Cast">
          {heading("Cast")}
          {cast.map(row)}
        </div>
      ) : null}
      {docs.length ? (
        <div role="group" aria-label="Context files">
          {heading("Context files")}
          {docs.map(row)}
        </div>
      ) : null}
    </div>
  );
}
