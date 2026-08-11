import { beforeEach, describe, it, expect, vi } from "vitest";
import {
  applyTriage,
  BLANK_FIELDS,
  commitWorld,
  docToContextInput,
  draftDocTexts,
  fromContextDocument,
  persistStatsDiff,
  toCreatorDoc,
} from "./storylineCreator";
import { blankStat } from "./editor";
import * as api from "@/lib/api";
import type { ContextDocument, StatDefinition } from "@/lib/types";

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
  it("a fresh doc starts untriaged: Select (uncategorized), Draft on, RAG on, Extract off", () => {
    const d = toCreatorDoc({ name: "a.md", text: "x" });
    expect(d.category).toBe("select");
    expect(d.triaged).toBe(false);
    // Draft is ON by default — an uploaded file the assistant cannot see is the
    // surprising case. Bounded by DOCS_CHAR_CAP and reversible via De-select All.
    expect(d.useDraft).toBe(true);
    expect(d.useRag).toBe(true);
    // Extraction is opt-in — a new doc is never auto-mined.
    expect(d.useExtract).toBe(false);
  });

  it("toCreatorDoc applies an upload target (category + Draft/RAG/Extract) and marks it triaged", () => {
    const d = toCreatorDoc(
      { name: "hero.md", text: "x" },
      { category: "character", useDraft: true, useRag: false, useExtract: true },
    );
    expect(d.category).toBe("character");
    expect(d.triaged).toBe(true); // a real category counts as already sorted
    expect(d.useDraft).toBe(true);
    expect(d.useRag).toBe(false);
    expect(d.useExtract).toBe(true);
  });

  it("toCreatorDoc with an explicit 'select' target stays Uncategorized + untriaged", () => {
    const d = toCreatorDoc({ name: "a.md", text: "x" }, { category: "select" });
    expect(d.category).toBe("select");
    expect(d.triaged).toBe(false);
  });

  it("applyTriage merges classifications by name (incl. the Extract suggestion)", () => {
    const docs = [toCreatorDoc({ name: "a.md", text: "x" }), toCreatorDoc({ name: "b.md", text: "y" })];
    const merged = applyTriage(docs, [
      { name: "a.md", category: "character", includeDraft: false, includeRag: true, includeExtract: true },
      { name: "b.md", category: "other", includeDraft: true, includeRag: true, includeExtract: false },
    ]);
    expect(merged[0].category).toBe("character");
    expect(merged[0].triaged).toBe(true);
    expect(merged[0].useExtract).toBe(true);
    expect(merged[1].useDraft).toBe(true);
    expect(merged[1].useExtract).toBe(false);
  });

  it("docToContextInput and fromContextDocument round-trip includeExtract", () => {
    const input = docToContextInput({
      ...toCreatorDoc({ name: "maerin.md", text: "x" }, { category: "character" }),
      useExtract: true,
    });
    expect(input.includeExtract).toBe(true);

    const back = fromContextDocument({
      id: "cd1", storylineId: "s", name: "maerin.md", content: "x",
      category: "character", includeDraft: false, includeRag: true, includeExtract: true,
      source: "upload", charCount: 1,
    });
    expect(back.useExtract).toBe(true);
  });

  it("draftDocTexts returns only the Draft-included doc texts", () => {
    const docs = [
      { ...toCreatorDoc({ name: "a.md", text: "AAA" }), useDraft: true },
      { ...toCreatorDoc({ name: "b.md", text: "BBB" }), useDraft: false },
    ];
    expect(draftDocTexts(docs)).toEqual(["AAA"]);
  });
});

describe("storylineCreator.commitWorld create mode", () => {
  it("creates the storyline, its stats, then the triaged corpus", async () => {
    const id = await commitWorld({
      fields: { ...BLANK_FIELDS, title: "World" },
      stats: [HEALTH],
      statsOriginal: [],
      docs: [{ name: "lore.md", text: "x", category: "other", triaged: true }],
    });
    expect(id).toBeTruthy();
    expect(vi.mocked(api.createStoryline)).toHaveBeenCalledWith(
      expect.objectContaining({ title: "World" }),
    );
    expect(vi.mocked(api.createStatDefinition)).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ key: "health" }),
    );
    expect(vi.mocked(api.bulkCreateContextDocuments)).toHaveBeenCalledWith(
      expect.any(String),
      [expect.objectContaining({ name: "lore.md" })],
    );
  });
});

describe("storylineCreator.commitWorld edit-mode corpus reconcile", () => {
  beforeEach(() => vi.clearAllMocks());

  function ctx(over: Partial<ContextDocument> & { id: string; name: string }): ContextDocument {
    return {
      storylineId: "w", content: "x", category: "other", includeDraft: false,
      includeRag: true, source: "upload", charCount: 1, ...over,
    } as ContextDocument;
  }

  it("creates new storyline docs and deletes removed ones (pruning embeddings)", async () => {
    const existingDocs: ContextDocument[] = [
      ctx({ id: "cd-keep", name: "keep.md" }),
      ctx({ id: "cd-gone", name: "gone.md" }),
      ctx({ id: "cd-entity", name: "char.md", category: "character", entityType: "character", entityId: "c1" }),
    ];
    await commitWorld({
      editId: "w",
      fields: { ...BLANK_FIELDS, title: "World" },
      stats: [],
      statsOriginal: [],
      docs: [
        { name: "keep.md", text: "x", category: "other", triaged: true },
        { name: "new.md", text: "n", category: "other", triaged: true },
      ],
      existingDocs,
    });
    // New storyline-level doc is created…
    expect(vi.mocked(api.bulkCreateContextDocuments)).toHaveBeenCalledWith("w", [
      expect.objectContaining({ name: "new.md" }),
    ]);
    // …the removed one is deleted (embedding pruned)…
    expect(vi.mocked(api.deleteContextDocument)).toHaveBeenCalledWith("cd-gone");
    // …and the kept + entity-scoped docs are left alone.
    expect(vi.mocked(api.deleteContextDocument)).not.toHaveBeenCalledWith("cd-keep");
    expect(vi.mocked(api.deleteContextDocument)).not.toHaveBeenCalledWith("cd-entity");
  });
});
