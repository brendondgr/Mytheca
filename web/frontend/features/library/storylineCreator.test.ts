import { beforeEach, describe, it, expect, vi } from "vitest";
import {
  applyTriage,
  BLANK_FIELDS,
  commitWorld,
  docToContextInput,
  draftDocTexts,
  fromContextDocument,
  persistStatsDiff,
  runPopulate,
  toCreatorDoc,
} from "./storylineCreator";
import { buildSummary, type BuildState } from "./worldBuild";
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

  it("never populates on its own — the build is the dialog's to run and show", async () => {
    await commitWorld({
      fields: { ...BLANK_FIELDS, title: "World" },
      stats: [],
      statsOriginal: [],
      docs: [],
    });
    expect(vi.mocked(api.populateWorldStream)).not.toHaveBeenCalled();
  });
});

// The build is what the author watches, so its state has to be reported truthfully:
// every entity that landed, every non-fatal problem, and — the bug this replaced —
// a stream that stops early must be a failure, not a silent success.
describe("storylineCreator.runPopulate", () => {
  const DOCS = "The tide charts are kept in the ledger house.";

  it("streams the run into build state and finishes on done", async () => {
    const seen: BuildState[] = [];
    const final = await runPopulate(
      "w1",
      { enabled: true, withArtwork: false },
      DOCS,
      (s) => seen.push(s),
    );

    expect(vi.mocked(api.populateWorldStream)).toHaveBeenCalledWith(
      "w1",
      { docsOverview: DOCS, withArtwork: false },
      undefined,
    );
    expect(final.phase).toBe("done");
    expect(final.entities.map((e) => e.name)).toEqual([
      "Maerin Voss",
      "Harbormaster Cael",
      "The Salt Wharf",
    ]);
    expect(final.entities[0].role).toBe("Smuggler");
    expect(final.problems).toEqual([]);
    // The dialog is fed every step, not just the outcome.
    expect(seen.some((s) => s.step.includes("Writing Maerin Voss"))).toBe(true);
  });

  it("treats a stream that ends without done as a failure", async () => {
    vi.mocked(api.populateWorldStream).mockImplementationOnce(async function* () {
      yield {
        type: "entity" as const,
        stage: "character" as const,
        id: "c1",
        name: "Maerin",
        role: "Smuggler",
        image: null,
      };
    } as never);

    const final = await runPopulate("w1", { enabled: true, withArtwork: false }, DOCS, () => {});

    expect(final.phase).toBe("failed");
    expect(final.error).toMatch(/only partly built/i);
    expect(final.entities).toHaveLength(1);
  });

  it("keeps going after a non-fatal problem and still finishes", async () => {
    vi.mocked(api.populateWorldStream).mockImplementationOnce(async function* () {
      yield { type: "error" as const, message: "Could not write Maerin.", fatal: false };
      yield {
        type: "entity" as const,
        stage: "setting" as const,
        id: "s1",
        name: "The Wharf",
        role: "Social Hub",
        image: null,
      };
      yield { type: "done" as const, characters: 0, settings: 1 };
    } as never);

    const final = await runPopulate("w1", { enabled: true, withArtwork: false }, DOCS, () => {});

    expect(final.phase).toBe("done");
    expect(final.problems).toEqual(["Could not write Maerin."]);
    expect(buildSummary(final)).toBe("0 characters · 1 setting");
  });

  it("reports a fatal frame as the failure it is", async () => {
    vi.mocked(api.populateWorldStream).mockImplementationOnce(async function* () {
      yield { type: "error" as const, message: "Choose a model in Options first.", fatal: true };
    } as never);

    const final = await runPopulate("w1", { enabled: true, withArtwork: false }, DOCS, () => {});

    expect(final.phase).toBe("failed");
    expect(final.error).toBe("Choose a model in Options first.");
  });

  it("never throws when the connection drops", async () => {
    vi.mocked(api.populateWorldStream).mockImplementationOnce(async function* () {
      throw new Error("Could not reach the server.");
    } as never);

    const final = await runPopulate("w1", { enabled: true, withArtwork: false }, DOCS, () => {});

    expect(final.phase).toBe("failed");
    expect(final.error).toBe("Could not reach the server.");
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
