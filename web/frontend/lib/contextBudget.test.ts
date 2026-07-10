import { describe, expect, it } from "vitest";
import {
  AVG_CHARS_PER_BEAT,
  beatsTokensFromTexts,
  budgetFor,
  CHARS_PER_TOKEN,
  DRAFT_DOCS_CAP_TOKENS,
  estimateBeatsTokens,
  estimateTokens,
  estimateUsedTokens,
  fmtTokensK,
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

  describe("beatsTokensFromTexts", () => {
    it("sums estimateTokens over the last `beats` real beat texts", () => {
      const texts = ["abcd", "abcdefgh", "ab", "abcdefghijkl"]; // 1, 2, 1, 3 tokens
      // Last 2 beats → 1 + 3 = 4.
      expect(beatsTokensFromTexts(texts, 2)).toBe(1 + 3);
      // All 4 → 1 + 2 + 1 + 3 = 7.
      expect(beatsTokensFromTexts(texts, 10)).toBe(1 + 2 + 1 + 3);
    });

    it("is 0 for an empty transcript or a zero/negative window", () => {
      expect(beatsTokensFromTexts([], 14)).toBe(0);
      expect(beatsTokensFromTexts(["abcd"], 0)).toBe(0);
      expect(beatsTokensFromTexts(["abcd"], -3)).toBe(0);
    });
  });

  describe("estimateUsedTokens", () => {
    it("returns 0 for an empty array", () => {
      expect(estimateUsedTokens([])).toBe(0);
    });

    it("sums estimated tokens across all beat strings", () => {
      // "abcd" = ceil(4/4) = 1 token, "efghijkl" = ceil(8/4) = 2 tokens → 3 total
      expect(estimateUsedTokens(["abcd", "efghijkl"])).toBe(3);
    });

    it("handles empty strings in the array", () => {
      expect(estimateUsedTokens(["", "", "abcd"])).toBe(1);
    });
  });

  describe("fmtTokensK", () => {
    it("formats sub-1K values with one decimal", () => {
      expect(fmtTokensK(500)).toBe("0.5K");
    });

    it("formats values between 1K–10K with one decimal, dropping .0", () => {
      expect(fmtTokensK(5200)).toBe("5.2K");
      expect(fmtTokensK(5000)).toBe("5K");
    });

    it("formats exact round-thousands without a decimal", () => {
      expect(fmtTokensK(16000)).toBe("16K");
    });

    it("formats non-round thousands with one decimal", () => {
      // 16384 / 1000 = 16.384, rounded to 1dp = 16.4
      expect(fmtTokensK(16384)).toBe("16.4K");
    });

    it("handles 0", () => {
      expect(fmtTokensK(0)).toBe("0K");
    });

    it("handles negative input as 0", () => {
      expect(fmtTokensK(-100)).toBe("0K");
    });
  });
});
