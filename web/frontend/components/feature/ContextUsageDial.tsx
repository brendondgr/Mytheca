"use client";

import { fmtTokensK } from "@/lib/contextBudget";

/**
 * Circular context-usage dial: a small **button** whose ring fills with the share of the
 * model's context window the live turn actually used, colour-coded by fill percentage:
 *   < 50%  → success green
 *   50–75% → gold (caution)
 *   ≥ 75%  → danger red
 *
 * The ring is purely visual — no number in the centre. Hovering (or keyboard-focusing) the
 * button reveals a tooltip with the exact usage (`8.3K of 16K tokens · 51% · exact`); the
 * same text is the button's `aria-label` for screen readers. Sits in the composer's bottom
 * controls row, left of Send.
 *
 * Renders nothing when `maxTokens` is 0 or negative (model limit unknown).
 */
export function ContextUsageDial({
  usedTokens,
  maxTokens,
  exact = false,
  size = 24,
}: {
  usedTokens: number;
  maxTokens: number;
  /** True when `usedTokens` is the model's reported `usage.prompt_tokens` (not an estimate). */
  exact?: boolean;
  /** Diameter in px (default 24). */
  size?: number;
}) {
  if (maxTokens <= 0) return null;

  const pct = Math.max(0, Math.min(100, (usedTokens / maxTokens) * 100));

  // SVG ring geometry — stroke scales with the (small) diameter so the ring stays crisp.
  const stroke = Math.max(3, Math.round(size / 9));
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - pct / 100);

  const colorClass = pct >= 75 ? "text-danger-ink" : pct >= 50 ? "text-gold-ink" : "text-success-ink";

  const usedFmt = fmtTokensK(usedTokens);
  const maxFmt = fmtTokensK(maxTokens);
  const qualifier = exact ? "exact" : "estimated";
  // "5.2K / 16K" is a number, not an explanation. The tooltip says what the number MEANS —
  // how much of what the model can read at once this scene is currently using — and only then
  // gives the figures.
  const detail =
    `How much of what the model can read at once this scene is using: ` +
    `${usedFmt} of ${maxFmt} tokens (${Math.round(pct)}%, ${qualifier}).`;

  return (
    <div className="group relative flex-none">
      <button
        type="button"
        aria-label={`Context usage: ${detail}`}
        className={`grid cursor-help place-items-center rounded-full transition-[filter] hover:brightness-110 focus-visible:outline-none ${colorClass}`}
        style={{ width: size, height: size }}
      >
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
          {/* Track — the unfilled ring. */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="var(--color-field-bd)"
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
      </button>
      {/* Hover / focus tooltip — the usage readout, above the dial (composer sits low). */}
      <span
        role="tooltip"
        // `whitespace-nowrap` around a full sentence made this tooltip 670px
        // wide — nearly twice a 390px viewport, and 2x a 320px one. It was
        // invisible as a bug because the shell clips with `overflow-hidden`, so
        // no page-level overflow check saw it; the tooltip simply ran off the
        // screen when shown. It now wraps and is bounded by the viewport.
        className="pointer-events-none absolute bottom-full left-1/2 mb-xs w-max max-w-[min(18rem,calc(100vw-2rem))] -translate-x-1/2 rounded-sm border border-cardbd bg-card px-sm py-2xs font-mono text-eyebrow tracking-[0.02em] text-ink opacity-0 shadow-md transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {detail}
      </span>
    </div>
  );
}
