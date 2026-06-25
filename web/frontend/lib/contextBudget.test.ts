import { describe, expect, it } from "vitest";
import {
  budgetFor,
  DRAFT_DOCS_CAP_TOKENS,
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
});
