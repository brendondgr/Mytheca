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
export const AVG_CHARS_PER_BEAT = 180;

/**
 * Estimate the tokens a context window of `beats` recent beats costs, from an average
 * beat length and the char/4 heuristic. Approximate, for the UI readout as the slider moves.
 */
export function estimateBeatsTokens(beats: number): number {
  return Math.ceil((Math.max(0, beats) * AVG_CHARS_PER_BEAT) / CHARS_PER_TOKEN);
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
