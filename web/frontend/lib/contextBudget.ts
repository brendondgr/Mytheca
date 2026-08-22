// Context-budget estimation for the New Storyline page.
//
// Two things spend model context: the **World Primer** (injected into EVERY scene,
// so it is a recurring per-scene cost) and the **Draft-included documents** (used to
// ground creation-time generation; truncated server-side). The page surfaces both as
// a meter so the author keeps the always-injected primer lean. A char/4 heuristic —
// no tokenizer dependency; close enough to steer authoring decisions.

/** Rough characters per token for English prose. */
export const CHARS_PER_TOKEN = 4;

/** Soft cap (tokens) on the World Primer — it rides along in every scene. */
export const PRIMER_SOFT_CAP_TOKENS = 1500;

/** Grounding cap (tokens) — draft docs are truncated to ~32000 chars server-side. */
export const DRAFT_DOCS_CAP_TOKENS = 8000;

export type BudgetLevel = "ok" | "warn" | "over";

/** Estimate the token count of a piece of text (ceil of chars / 4). */
export function estimateTokens(text: string | null | undefined): number {
  return Math.ceil((text?.length ?? 0) / CHARS_PER_TOKEN);
}

/**
 * Rough average characters in one transcript beat (a short line of dialogue, action, or
 * narration). Used only to give the scene-config menu a live, ballpark token estimate for a
 * chosen context-window depth — not an exact count.
 */
// `estimateBeatsTokens` and `AVG_CHARS_PER_BEAT` were deleted with the "Number of beats"
// slider: a flat 180-chars-per-beat average existed only to move a readout as the slider
// moved, and there is no slider. `beatsTokensFromTexts` below survives because it measures
// the real transcript, which Phase 5's "what this scene costs" readout still needs.

/**
 * Estimate the tokens the last `beats` of the ACTUAL transcript occupy, from each beat's
 * real text (char/4). Content-real — it reflects what the player has actually written and
 * the characters have actually said, not a flat average — so the scene-config readout tracks
 * the true recent-context size as the slider moves. `texts` is one string per beat (its
 * concatenated dialogue/action/thought). Still an estimate (no client tokenizer), but far
 * closer than the average; the exact figure lives on the context dial after a turn runs.
 */
export function beatsTokensFromTexts(texts: string[], beats: number): number {
  const n = Math.max(0, Math.floor(beats));
  if (n === 0) return 0; // guard: slice(-0) === slice(0) would sum the whole array
  return texts.slice(-n).reduce((sum, t) => sum + estimateTokens(t), 0);
}

export interface ContextBudget {
  /** Per-scene cost: the World Primer is injected into every scene. */
  primerTokens: number;
  /** Build-time grounding: the Draft-included documents (truncated to the cap). */
  draftDocsTokens: number;
  totalTokens: number;
  /** Worst of (primer vs. its soft cap) and (docs vs. the grounding cap). */
  level: BudgetLevel;
  primerSoftCap: number;
  draftDocsCap: number;
}

const RANK: Record<BudgetLevel, number> = { ok: 0, warn: 1, over: 2 };

function worst(a: BudgetLevel, b: BudgetLevel): BudgetLevel {
  return RANK[a] >= RANK[b] ? a : b;
}

/**
 * Estimate the total tokens consumed by a set of transcript beat texts (the live
 * context window). Pass each beat's concatenated text + action + thought strings.
 * Uses the same char/4 heuristic as `estimateTokens`.
 */
export function estimateUsedTokens(texts: string[]): number {
  return texts.reduce((sum, t) => sum + estimateTokens(t), 0);
}

/**
 * Format a token count as a compact "K" string for hover readouts (e.g. `5K / 16K`).
 *
 * Rule: divide by 1000, round to one decimal, then drop the ".0" suffix:
 *   - 500      → "0.5K"
 *   - 5200     → "5.2K"
 *   - 16000    → "16K"
 *   - 16384    → "16.4K"
 *
 * Always returns a "K" value (never raw tokens) so the caller can safely concatenate
 * with a static "K" suffix omitted — it is already included.
 */
export function fmtTokensK(n: number): string {
  const k = Math.round((Math.max(0, n) / 1000) * 10) / 10;
  return `${k % 1 === 0 ? k.toFixed(0) : k.toFixed(1)}K`;
}

/** Compute the context budget from the primer + the Draft-included doc texts. */
export function budgetFor(input: {
  worldPrimer?: string | null;
  draftDocs?: string[];
}): ContextBudget {
  const primerTokens = estimateTokens(input.worldPrimer);
  const draftDocsTokens = (input.draftDocs ?? []).reduce(
    (sum, text) => sum + estimateTokens(text),
    0,
  );

  const primerLevel: BudgetLevel =
    primerTokens > PRIMER_SOFT_CAP_TOKENS * 2
      ? "over"
      : primerTokens > PRIMER_SOFT_CAP_TOKENS
        ? "warn"
        : "ok";
  const docsLevel: BudgetLevel =
    draftDocsTokens > DRAFT_DOCS_CAP_TOKENS
      ? "over"
      : draftDocsTokens > DRAFT_DOCS_CAP_TOKENS * 0.8
        ? "warn"
        : "ok";

  return {
    primerTokens,
    draftDocsTokens,
    totalTokens: primerTokens + draftDocsTokens,
    level: worst(primerLevel, docsLevel),
    primerSoftCap: PRIMER_SOFT_CAP_TOKENS,
    draftDocsCap: DRAFT_DOCS_CAP_TOKENS,
  };
}
