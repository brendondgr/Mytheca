import { beforeEach, describe, it, expect, vi } from "vitest";
import { applyTriage, draftDocTexts, persistStatsDiff, toCreatorDoc } from "./storylineCreator";
import { blankStat } from "./editor";
import * as api from "@/lib/api";
import type { StatDefinition } from "@/lib/types";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

beforeEach(() => vi.clearAllMocks());

const HEALTH: StatDefinition = {
  key: "health",
  displayName: "Health",
  description: "Vitality.",
  min: 0,
  max: 100,
  default: 100,
  visibility: "public",
  guidance: null,
  appliesTo: ["character"],
  bands: [{ min: 0, max: 20, label: "Nearly dead" }],
};

describe("storylineCreator.persistStatsDiff", () => {
  it("diffs current vs original into create / update / delete", async () => {
    const original = [HEALTH, { ...blankStat(), key: "trust", displayName: "Trust" }];
    const editedHealth = { ...HEALTH, default: 80 };
    const morale = { ...blankStat(), key: "morale", displayName: "Morale" };
    // Keep health (edited), drop trust, add morale.
    await persistStatsDiff("w1", [editedHealth, morale], original);

    expect(vi.mocked(api.deleteStatDefinition)).toHaveBeenCalledWith("w1", "trust");
    expect(vi.mocked(api.updateStatDefinition)).toHaveBeenCalledWith(
      "w1",
      "health",
      expect.objectContaining({ default: 80 }),
    );
    expect(vi.mocked(api.createStatDefinition)).toHaveBeenCalledWith(
      "w1",
      expect.objectContaining({ key: "morale", displayName: "Morale" }),
    );
  });

  it("skips blank (unnamed) stat rows", async () => {
    await persistStatsDiff("w1", [blankStat()], []);
    expect(vi.mocked(api.createStatDefinition)).not.toHaveBeenCalled();
  });
});

describe("storylineCreator helpers", () => {
  it("a fresh doc starts untriaged: Other, RAG on, Draft off", () => {
    const d = toCreatorDoc({ name: "a.md", text: "x" });
    expect(d.category).toBe("other");
    expect(d.triaged).toBe(false);
    expect(d.useDraft).toBe(false);
    expect(d.useRag).toBe(true);
  });

  it("applyTriage merges classifications by name", () => {
    const docs = [toCreatorDoc({ name: "a.md", text: "x" }), toCreatorDoc({ name: "b.md", text: "y" })];
    const merged = applyTriage(docs, [
      { name: "a.md", category: "character", includeDraft: false, includeRag: true },
      { name: "b.md", category: "other", includeDraft: true, includeRag: true },
    ]);
    expect(merged[0].category).toBe("character");
    expect(merged[0].triaged).toBe(true);
    expect(merged[1].useDraft).toBe(true);
  });

  it("draftDocTexts returns only the Draft-included doc texts", () => {
    const docs = [
      { ...toCreatorDoc({ name: "a.md", text: "AAA" }), useDraft: true },
      { ...toCreatorDoc({ name: "b.md", text: "BBB" }), useDraft: false },
    ];
    expect(draftDocTexts(docs)).toEqual(["AAA"]);
  });
});
