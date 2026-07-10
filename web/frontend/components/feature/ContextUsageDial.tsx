"use client";

import { fmtTokensK } from "@/lib/contextBudget";

/**
 * Circular context-usage dial: a small ring that fills with the share of the model's
 * context window the live turn actually used, colour-coded by fill percentage:
 *   < 50%  → success green
 *   50–75% → gold (caution)
 *   ≥ 75%  → danger red
 *
 * The centre shows the used-token count (compact "K"); the hover title + `aria-valuetext`
 * spell out `"8.3K of 16K tokens"` and whether the figure is the model's EXACT reported
 * usage or the char/4 estimate. Sits in the composer's bottom row, left of Send.
 *
 * Renders nothing when `maxTokens` is 0 or negative (model limit unknown) — same as the
 * bar it replaces, so the composer simply omits the dial rather than showing a bogus ring.
 */
export function ContextUsageDial({
  usedTokens,
  maxTokens,
  exact = false,
  size = 40,
}: {
  usedTokens: number;
  maxTokens: number;
  /** True when `usedTokens` is the model's reported `usage.prompt_tokens` (not an estimate). */
  exact?: boolean;
  /** Diameter in px (default 40). */
  size?: number;
}) {
  if (maxTokens <= 0) return null;

  const pct = Math.max(0, Math.min(100, (usedTokens / maxTokens) * 100));

  // SVG ring geometry: a 4-px stroke inset from the edge so the round caps never clip.
  const stroke = 4;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - pct / 100);

  const colorClass = pct >= 75 ? "text-danger" : pct >= 50 ? "text-gold" : "text-success";

  const usedFmt = fmtTokensK(usedTokens);
  const maxFmt = fmtTokensK(maxTokens);
  const qualifier = exact ? "exact" : "estimated";
  const valueText = `${usedFmt} of ${maxFmt} tokens (${qualifier})`;

  return (
    <div
      role="progressbar"
      aria-label="Context usage"
      aria-valuenow={usedTokens}
      aria-valuemin={0}
      aria-valuemax={maxTokens}
      aria-valuetext={valueText}
      title={`${usedFmt} / ${maxFmt} tokens · ${qualifier}`}
      className={`relative grid flex-none place-items-center ${colorClass}`}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        {/* Track — the unfilled ring. */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--color-field)"
          strokeWidth={stroke}
        />
        {/* Value arc — starts at 12 o'clock, fills clockwise, coloured by band. */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          className="transition-[stroke-dashoffset] duration-300 motion-reduce:transition-none"
        />
      </svg>
      {/* Centre readout — the used-token count (compact K). */}
      <span className="absolute font-mono text-[8px] leading-none tracking-tight text-ink tabular-nums">
        {usedFmt}
      </span>
    </div>
  );
}
