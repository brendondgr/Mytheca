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

  const colorClass = pct >= 75 ? "text-danger" : pct >= 50 ? "text-gold" : "text-success";

  const usedFmt = fmtTokensK(usedTokens);
  const maxFmt = fmtTokensK(maxTokens);
  const qualifier = exact ? "exact" : "estimated";
  const detail = `${usedFmt} of ${maxFmt} tokens · ${Math.round(pct)}% · ${qualifier}`;

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
        className="pointer-events-none absolute bottom-full left-1/2 mb-[7px] -translate-x-1/2 whitespace-nowrap rounded-[6px] border border-cardbd bg-card px-[9px] py-[5px] font-mono text-[10px] tracking-[0.02em] text-ink opacity-0 shadow-[0_6px_18px_rgba(20,14,6,.20)] transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {detail}
      </span>
    </div>
  );
}
