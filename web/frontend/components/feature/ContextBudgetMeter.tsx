"use client";

import { Eyebrow } from "@/components/ui/Eyebrow";
import { cn } from "@/lib/cn";
import type { ContextBudget } from "@/lib/contextBudget";

const LEVEL_TEXT: Record<ContextBudget["level"], string> = {
  ok: "text-ink-soft",
  warn: "text-gold-ink",
  over: "text-danger-ink",
};
const LEVEL_BAR: Record<ContextBudget["level"], string> = {
  ok: "bg-accent",
  warn: "bg-gold",
  over: "bg-danger",
};
const LEVEL_NOTE: Record<ContextBudget["level"], string> = {
  ok: "Lean — comfortably within the per-scene budget.",
  warn: "Getting heavy — trim the World Primer or the Draft docs.",
  over: "Over budget — the primer / grounding will be truncated.",
};

function fmtTokens(n: number): string {
  if (n < 1000) return String(n);
  const k = Math.round((n / 1000) * 10) / 10;
  return `${k % 1 === 0 ? k.toFixed(0) : k.toFixed(1)}K`;
}

/**
 * Advisory meter estimating the context the always-injected World Primer (a
 * per-scene cost) and the Draft-included documents (creation-time grounding) will
 * spend. A char/4 token heuristic; it steers authoring, it does not block.
 */
export function ContextBudgetMeter({ budget }: { budget: ContextBudget }) {
  const pct = Math.min(
    100,
    Math.round((budget.primerTokens / budget.primerSoftCap) * 100) || 0,
  );
  return (
    <div role="status" className="rounded-sm border border-cardbd bg-field px-md py-sm">
      <div className="flex items-center justify-between">
        <Eyebrow size={9.5} tracking="0.14em" entity="#A8762A">
          ⚖ Context budget
        </Eyebrow>
        <span className={cn("font-mono text-eyebrow font-medium", LEVEL_TEXT[budget.level])}>
          ~{fmtTokens(budget.totalTokens)} tok
        </span>
      </div>
      <div
        className="mt-sm h-[6px] w-full overflow-hidden rounded-full bg-card2"
        role="progressbar"
        aria-valuenow={budget.primerTokens}
        aria-valuemin={0}
        aria-valuemax={budget.primerSoftCap}
        aria-label="World Primer size against its per-scene budget"
      >
        {/* scaleX rather than width — a compositor-only property, so the fill
            never triggers layout. See the same note in DirectorRail. */}
        <div
          className={cn(
            "h-full w-full origin-left rounded-full transition-transform duration-base ease-out",
            LEVEL_BAR[budget.level],
          )}
          style={{ transform: `scaleX(${pct / 100})` }}
        />
      </div>
      <dl className="mt-sm flex flex-col gap-2xs font-mono text-eyebrow">
        <div className="flex justify-between gap-sm">
          <dt className="text-ink-soft">World Primer · every scene</dt>
          <dd className="text-ink">~{fmtTokens(budget.primerTokens)}</dd>
        </div>
        <div className="flex justify-between gap-sm">
          <dt className="text-ink-soft">Draft docs · grounding</dt>
          <dd className="text-ink">~{fmtTokens(budget.draftDocsTokens)}</dd>
        </div>
      </dl>
      <p className={cn("mt-xs font-body text-label", LEVEL_TEXT[budget.level])}>
        {LEVEL_NOTE[budget.level]}
      </p>
    </div>
  );
}
