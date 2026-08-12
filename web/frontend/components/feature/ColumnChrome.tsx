/** Shared chrome for the Library's three open columns: a header + empty note. */

import { cn } from "@/lib/cn";

export function ColumnHeader({
  title,
  count,
  hint,
  onAdd,
  addLabel,
  className,
}: {
  title: string;
  count: number;
  hint?: string;
  onAdd?: () => void;
  addLabel?: string;
  className?: string;
}) {
  // Sticky so the column's identity stays visible while its content scrolls.
  // The outer wrapper has no horizontal padding so bg-page covers the full
  // column width (edge-to-edge). Horizontal padding lives on the inner div
  // via the className prop so content aligns with the cards below.
  return (
    <div className="sticky top-0 z-[10] bg-page pb-[12px]">
      <div className={cn("border-b border-hair-strong pb-[8px]", className)}>
        <div className="flex items-center justify-between gap-[8px]">
          <div className="flex items-baseline gap-[8px]">
            <h2 className="font-display text-[16px] font-semibold tracking-[0.06em] text-ink uppercase">
              {title}
            </h2>
            <span className="font-mono text-[11px] text-mute">{count}</span>
          </div>
          {onAdd ? (
            <button
              type="button"
              aria-label={addLabel ?? `Add ${title.toLowerCase()}`}
              onClick={onAdd}
              className="cursor-pointer rounded-[4px] px-[3px] font-mono text-[18px] leading-none text-mute transition-colors hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              +
            </button>
          ) : null}
        </div>
        {hint ? (
          <p className="mt-[5px] font-mono text-[9.5px] tracking-[0.05em] text-mute">
            {hint}
          </p>
        ) : null}
      </div>
    </div>
  );
}

/**
 * A column with nothing in it.
 *
 * Two genuinely different situations, and they need different answers:
 *
 * - **A search found nothing.** The content exists; the query is wrong. The
 *   only useful affordance is clearing the search, so that is what is offered.
 * - **The column is empty.** This is the author's first visit to it, and a
 *   flat "No characters yet." is a dead end. An empty state is an invitation
 *   to act, so it says what the thing *is* and carries its create action
 *   inline — the same action buried in the column header's `+`, put where
 *   someone who has never seen the app will actually look.
 */
export function ColumnEmpty({
  query,
  noun,
  invitation,
  onAdd,
  addLabel,
  onClearQuery,
}: {
  query: string;
  noun: string;
  /** One line on what this kind of thing is for. Shown only when unfiltered. */
  invitation?: string;
  onAdd?: () => void;
  addLabel?: string;
  onClearQuery?: () => void;
}) {
  if (query) {
    return (
      <div className="flex flex-col items-center gap-[10px] py-[24px] text-center">
        <p className="font-body text-body-sm text-mute2 italic">
          No {noun} match “{query}”.
        </p>
        {onClearQuery ? (
          <button
            type="button"
            onClick={onClearQuery}
            className="press cursor-pointer rounded-[3px] font-mono text-[11px] tracking-[0.08em] text-accent uppercase transition-colors duration-fast ease-soft hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            Clear search
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-[10px] rounded-[4px] border border-dashed border-cardbd px-[16px] py-[24px] text-center">
      <p className="font-display text-[14px] font-semibold text-ink">
        <span aria-hidden className="mr-[6px] text-gold">
          ❖
        </span>
        No {noun} yet
      </p>
      {invitation ? (
        <p className="max-w-[34ch] font-body text-body-sm leading-[1.5] text-ink-soft">
          {invitation}
        </p>
      ) : null}
      {onAdd ? (
        <button
          type="button"
          onClick={onAdd}
          className="press touch-target cursor-pointer rounded-[2px] border border-accent px-[14px] py-[7px] font-mono text-[11px] tracking-[0.08em] text-accent uppercase transition-colors duration-fast ease-soft hover:bg-accent hover:text-[#F6ECDA] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {addLabel ?? `Add ${noun.replace(/s$/, "")}`}
        </button>
      ) : null}
    </div>
  );
}
