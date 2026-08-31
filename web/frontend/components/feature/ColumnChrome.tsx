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
  //
  // `lg`-only. Below that there is one column at a time, chosen by a tab bar that
  // already says its name and its count — so this header restated both, three words
  // under three identical words, and pushed the first card down a screenful. Its `+`
  // is not lost: `LibraryColumns` passes it to the tab bar's `action` slot.
  return (
    <div className="sticky top-0 z-[10] hidden bg-page pb-md lg:block">
      <div className={cn("border-b border-hair-strong pb-sm", className)}>
        <div className="flex items-center justify-between gap-sm">
          <div className="flex items-baseline gap-sm">
            <h2 className="font-display text-body font-semibold tracking-[0.06em] text-ink uppercase">
              {title}
            </h2>
            <span className="font-mono text-eyebrow text-mute">{count}</span>
          </div>
          {onAdd ? (
            <button
              type="button"
              aria-label={addLabel ?? `Add ${title.toLowerCase()}`}
              onClick={onAdd}
              className="cursor-pointer rounded-sm px-3xs font-mono text-step-1 leading-none text-mute transition-colors hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              +
            </button>
          ) : null}
        </div>
        {hint ? (
          <p className="mt-2xs font-mono text-eyebrow tracking-[0.05em] text-mute">
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
      <div className="flex flex-col items-center gap-sm py-xl text-center">
        <p className="font-body text-body-sm text-mute2 italic">
          No {noun} match “{query}”.
        </p>
        {onClearQuery ? (
          <button
            type="button"
            onClick={onClearQuery}
            className="press cursor-pointer rounded-xs font-mono text-eyebrow tracking-[0.08em] text-accent-ink uppercase transition-colors duration-fast ease-soft hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            Clear search
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-sm rounded-sm border border-dashed border-cardbd px-lg py-xl text-center">
      <p className="font-display text-body-sm font-semibold text-ink">
        <span aria-hidden className="mr-xs text-gold-ink">
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
          className="press touch-target cursor-pointer rounded-xs border border-accent px-lg py-xs font-mono text-eyebrow tracking-[0.08em] text-accent-ink uppercase transition-colors duration-fast ease-soft hover:bg-accent hover:text-[#F6ECDA] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {addLabel ?? `Add ${noun.replace(/s$/, "")}`}
        </button>
      ) : null}
    </div>
  );
}
