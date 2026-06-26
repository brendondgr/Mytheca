"use client";

import { Eyebrow } from "@/components/ui/Eyebrow";
import { cn } from "@/lib/cn";
import type { ContextBudget } from "@/lib/contextBudget";

const LEVEL_TEXT: Record<ContextBudget["level"], string> = {
  ok: "text-mute",
  warn: "text-gold",
  over: "text-danger",
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
    <div role="status" className="rounded-[4px] border border-cardbd bg-field px-[12px] py-[10px]">
      <div className="flex items-center justify-between">
        <Eyebrow size={8.5} tracking="0.14em" color="#A8762A">
          ⚖ Context budget
        </Eyebrow>
        <span className={cn("font-mono text-[10px]", LEVEL_TEXT[budget.level])}>
          ~{budget.totalTokens.toLocaleString()} tok
        </span>
      </div>
      <div
        className="mt-[8px] h-[6px] w-full overflow-hidden rounded-full bg-card2"
        role="progressbar"
        aria-valuenow={budget.primerTokens}
        aria-valuemin={0}
        aria-valuemax={budget.primerSoftCap}
        aria-label="World Primer size against its per-scene budget"
      >
        <div
          className={cn("h-full rounded-full transition-[width]", LEVEL_BAR[budget.level])}
          style={{ width: `${pct}%` }}
        />
      </div>
      <dl className="mt-[8px] flex flex-col gap-[3px] font-mono text-[10px] text-mute">
        <div className="flex justify-between gap-[8px]">
          <dt>World Primer · every scene</dt>
          <dd className="text-ink-soft">~{budget.primerTokens.toLocaleString()}</dd>
        </div>
        <div className="flex justify-between gap-[8px]">
          <dt>Draft docs · grounding</dt>
          <dd className="text-ink-soft">~{budget.draftDocsTokens.toLocaleString()}</dd>
        </div>
      </dl>
      <p className={cn("mt-[6px] font-body text-[11.5px]", LEVEL_TEXT[budget.level])}>
        {LEVEL_NOTE[budget.level]}
      </p>
    </div>
  );
}
