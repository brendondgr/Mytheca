import { describe, expect, it } from "vitest";
import {
  AVG_CHARS_PER_BEAT,
  budgetFor,
  CHARS_PER_TOKEN,
  DRAFT_DOCS_CAP_TOKENS,
  estimateBeatsTokens,
  estimateTokens,
  PRIMER_SOFT_CAP_TOKENS,
} from "@/lib/contextBudget";

describe("contextBudget", () => {
  it("estimates ~1 token per 4 chars", () => {
    expect(estimateTokens("")).toBe(0);
    expect(estimateTokens(null)).toBe(0);
    expect(estimateTokens("abcd")).toBe(1);
    expect(estimateTokens("abcde")).toBe(2); // ceil(5/4)
  });

  it("sums primer + draft-doc tokens", () => {
    const b = budgetFor({ worldPrimer: "a".repeat(40), draftDocs: ["b".repeat(40), "c".repeat(80)] });
    expect(b.primerTokens).toBe(10);
    expect(b.draftDocsTokens).toBe(30);
    expect(b.totalTokens).toBe(40);
  });

  it("stays ok under both caps", () => {
    expect(budgetFor({ worldPrimer: "short", draftDocs: ["short"] }).level).toBe("ok");
  });

  it("warns when the primer passes its soft cap", () => {
    const primer = "x".repeat((PRIMER_SOFT_CAP_TOKENS + 100) * 4);
    expect(budgetFor({ worldPrimer: primer }).level).toBe("warn");
  });

  it("flags over when draft docs exceed the grounding cap", () => {
    const docs = ["x".repeat((DRAFT_DOCS_CAP_TOKENS + 100) * 4)];
    expect(budgetFor({ draftDocs: docs }).level).toBe("over");
  });

  it("estimates beat-window tokens from beats × avg-chars ÷ chars-per-token", () => {
    // 14 beats × 180 chars ÷ 4 = 630.
    expect(estimateBeatsTokens(14)).toBe(
      Math.ceil((14 * AVG_CHARS_PER_BEAT) / CHARS_PER_TOKEN),
    );
    expect(estimateBeatsTokens(0)).toBe(0);
    // Monotonic: more beats → more tokens.
    expect(estimateBeatsTokens(100)).toBeGreaterThan(estimateBeatsTokens(5));
  });
});
