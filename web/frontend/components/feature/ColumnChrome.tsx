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
          <p className="mt-[5px] font-mono text-tag tracking-[0.05em] text-mute">
            {hint}
          </p>
        ) : null}
      </div>
    </div>
  );
}

export function ColumnEmpty({ query, noun }: { query: string; noun: string }) {
  return (
    <p className="py-[24px] text-center font-body text-[14px] text-mute2 italic">
      {query ? `No ${noun} match “${query}”.` : `No ${noun} yet.`}
    </p>
  );
}
