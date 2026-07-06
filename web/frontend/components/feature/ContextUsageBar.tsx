"use client";

import { fmtTokensK } from "@/lib/contextBudget";

/**
 * Slim full-width progress bar showing estimated token usage of the live context
 * window against the model's reported maximum. Colour-coded by fill percentage:
 *   < 50% → success green
 *   50–75% → gold (caution)
 *   ≥ 75% → danger red
 *
 * Renders nothing when `maxTokens` is 0 or negative (model limit unknown).
 */
export function ContextUsageBar({
  usedTokens,
  maxTokens,
}: {
  usedTokens: number;
  maxTokens: number;
}) {
  if (maxTokens <= 0) return null;

  const pct = Math.min(100, (usedTokens / maxTokens) * 100);

  const fillColor =
    pct >= 75
      ? "bg-danger"
      : pct >= 50
        ? "bg-gold"
        : "bg-success";

  const usedFmt = fmtTokensK(usedTokens);
  const maxFmt = fmtTokensK(maxTokens);
  const valueText = `${usedFmt} of ${maxFmt} tokens`;
  const titleText = `${usedFmt} / ${maxFmt} tokens`;

  return (
    <div
      role="progressbar"
      aria-label="Context usage"
      aria-valuenow={usedTokens}
      aria-valuemin={0}
      aria-valuemax={maxTokens}
      aria-valuetext={valueText}
      title={titleText}
      className="h-[6px] w-full overflow-hidden rounded-full bg-field"
    >
      <div
        className={`h-full rounded-full transition-[width] duration-300 motion-reduce:transition-none ${fillColor}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
