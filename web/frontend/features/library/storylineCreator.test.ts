import { beforeEach, describe, it, expect, vi } from "vitest";
import {
  applyTriage,
  BLANK_FIELDS,
  commitWorld,
  type CommitEntityPatch,
  docToContextInput,
  draftDocTexts,
  fromContextDocument,
  persistStatsDiff,
  proposedToCharacterInput,
  renderProposalImages,
  toCreatorDoc,
} from "./storylineCreator";
import { blankStat } from "./editor";
import * as api from "@/lib/api";
import type { ContextDocument, ProposedWorld, StatDefinition } from "@/lib/types";

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
  it("a fresh doc starts untriaged: Select (uncategorized), RAG on, Draft off, Extract off", () => {
    const d = toCreatorDoc({ name: "a.md", text: "x" });
    expect(d.category).toBe("select");
    expect(d.triaged).toBe(false);
    expect(d.useDraft).toBe(false);
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

  it("proposedToCharacterInput carries the generated voice samples into the create body", () => {
    const input = proposedToCharacterInput({
      name: "Maerin", role: "Smuggler", traits: "Wary", speech: "Clipped.",
      goal: "Out.", secret: "Informant.", appearance: "", background: "", personality: "",
      color: "#3A5A78",
      voiceSamples: [{ situation: "questioned", sample: "Ask again." }],
      startingStats: [],
    });
    expect(input.voiceSamples).toEqual([{ situation: "questioned", sample: "Ask again." }]);
  });
});

describe("storylineCreator.commitWorld image previews", () => {
  const PROPOSED: ProposedWorld = {
    storyline: { title: "W", genre: "G", tagline: "", premise: "", worldPrimer: "" },
    stats: [],
    characters: [
      {
        name: "Hero",
        role: "Lead",
        traits: "Bold",
        speech: "",
        goal: "",
        secret: "",
        appearance: "",
        background: "",
        personality: "",
        color: "#000",
        voiceSamples: [],
        startingStats: [],
      },
    ],
    settings: [
      { name: "Place", type: "Hub", desc: "", atmosphere: "", features: "", currentState: "" },
    ],
  };

  it("emits onEntity patches as each portrait / scene-art renders", async () => {
    const events: CommitEntityPatch[] = [];
    await commitWorld(
      {
        fields: { ...BLANK_FIELDS, title: "World" },
        stats: [],
        statsOriginal: [],
        proposed: PROPOSED,
        docs: [],
        generateImages: true,
      },
      undefined,
      (e) => events.push(e),
    );
    expect(events).toContainEqual({
      type: "character",
      index: 0,
      patch: { portrait: "/media/portraits/test.webp" },
    });
    expect(events).toContainEqual({
      type: "setting",
      index: 0,
      patch: { image: "/media/scenes/test.webp" },
    });
  });

  it("emits no entity patches when image generation is off", async () => {
    const events: CommitEntityPatch[] = [];
    await commitWorld(
      {
        fields: { ...BLANK_FIELDS, title: "World" },
        stats: [],
        statsOriginal: [],
        proposed: PROPOSED,
        docs: [],
        generateImages: false,
      },
      undefined,
      (e) => events.push(e),
    );
    expect(events).toHaveLength(0);
    expect(vi.mocked(api.generatePortrait)).not.toHaveBeenCalled();
  });

  it("renderProposalImages renders an image per entity (build-time, no persist)", async () => {
    const events: CommitEntityPatch[] = [];
    await renderProposalImages(PROPOSED, (e) => events.push(e));
    expect(events).toContainEqual({
      type: "character",
      index: 0,
      patch: { portrait: "/media/portraits/test.webp" },
    });
    expect(events).toContainEqual({
      type: "setting",
      index: 0,
      patch: { image: "/media/scenes/test.webp" },
    });
    // It only generates — nothing is persisted during the build (entities have no id).
    expect(vi.mocked(api.updateCharacter)).not.toHaveBeenCalled();
    expect(vi.mocked(api.updateSetting)).not.toHaveBeenCalled();
  });

  it("renderProposalImages skips entities that already have an image", async () => {
    const withImages = {
      ...PROPOSED,
      characters: [{ ...PROPOSED.characters[0], portrait: "/already.webp" }],
      settings: [{ ...PROPOSED.settings[0], image: "/already.webp" }],
    };
    const events: CommitEntityPatch[] = [];
    await renderProposalImages(withImages, (e) => events.push(e));
    expect(events).toHaveLength(0);
    expect(vi.mocked(api.generatePortrait)).not.toHaveBeenCalled();
    expect(vi.mocked(api.generateSceneArt)).not.toHaveBeenCalled();
  });

  it("renderProposalImages circuit-breaks on the first failed render (ComfyUI down)", async () => {
    vi.mocked(api.generatePortrait).mockRejectedValue(new Error("502"));
    const twoChars = {
      ...PROPOSED,
      characters: [
        { ...PROPOSED.characters[0], name: "A" },
        { ...PROPOSED.characters[0], name: "B" },
      ],
    };
    const events: CommitEntityPatch[] = [];
    await renderProposalImages(twoChars, (e) => events.push(e));
    // First portrait fails → stop; the 2nd character and all settings are skipped.
    expect(events).toHaveLength(0);
    expect(vi.mocked(api.generatePortrait)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(api.generateSceneArt)).not.toHaveBeenCalled();
  });

  it("commitWorld stops rendering after the first failure but still creates entities", async () => {
    vi.mocked(api.generatePortrait).mockRejectedValue(new Error("502"));
    const twoChars = {
      ...PROPOSED,
      characters: [
        { ...PROPOSED.characters[0], name: "A" },
        { ...PROPOSED.characters[0], name: "B" },
      ],
    };
    const id = await commitWorld({
      fields: { ...BLANK_FIELDS, title: "World" },
      stats: [],
      statsOriginal: [],
      proposed: twoChars,
      docs: [],
      generateImages: true,
    });
    expect(id).toBeTruthy();
    // Both characters created; only ONE portrait render attempted (then circuit-broke).
    expect(vi.mocked(api.createCharacter)).toHaveBeenCalledTimes(2);
    expect(vi.mocked(api.generatePortrait)).toHaveBeenCalledTimes(1);
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
      proposed: null,
      docs: [
        { name: "keep.md", text: "x", category: "other", triaged: true },
        { name: "new.md", text: "n", category: "other", triaged: true },
      ],
      existingDocs,
      generateImages: false,
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

describe("storylineCreator.commitWorld build lineage", () => {
  function proposedWithLineage(): ProposedWorld {
    return {
      storyline: { title: "W", genre: "G", tagline: "", premise: "", worldPrimer: "" },
      stats: [],
      characters: [
        {
          name: "Maerin", role: "Smuggler", traits: "", speech: "", goal: "", secret: "",
          appearance: "", background: "", personality: "", color: "#000",
          voiceSamples: [], startingStats: [], sourceDocNames: ["maerin.md"],
        },
      ],
      settings: [
        {
          name: "Chapel", type: "Sacred", desc: "", atmosphere: "", features: "",
          currentState: "", sourceDocNames: ["chapel.md"],
        },
      ],
    };
  }

  it("links each created entity to the corpus doc it was mined from", async () => {
    await commitWorld({
      fields: { ...BLANK_FIELDS, title: "World" },
      stats: [],
      statsOriginal: [],
      proposed: proposedWithLineage(),
      docs: [
        { name: "maerin.md", text: "smuggler", category: "character", triaged: true },
        { name: "chapel.md", text: "shrine", category: "setting", triaged: true },
      ],
      generateImages: false,
    });

    const createdDocs = await vi.mocked(api.bulkCreateContextDocuments).mock.results[0].value;
    const idByName = new Map(createdDocs.map((d: ContextDocument) => [d.name, d.id]));
    const createdChar = await vi.mocked(api.createCharacter).mock.results[0].value;
    const createdSetting = await vi.mocked(api.createSetting).mock.results[0].value;

    expect(vi.mocked(api.addDocumentLink)).toHaveBeenCalledWith(idByName.get("maerin.md"), {
      entityType: "character",
      entityId: createdChar.id,
    });
    expect(vi.mocked(api.addDocumentLink)).toHaveBeenCalledWith(idByName.get("chapel.md"), {
      entityType: "setting",
      entityId: createdSetting.id,
    });
  });

  it("creates no link when the source doc is not in the persisted corpus", async () => {
    const proposed = proposedWithLineage();
    proposed.settings = [];
    await commitWorld({
      fields: { ...BLANK_FIELDS, title: "World" },
      stats: [],
      statsOriginal: [],
      proposed,
      // The character cites maerin.md, but it was never uploaded (removed before commit).
      docs: [{ name: "other.md", text: "x", category: "other", triaged: true }],
      generateImages: false,
    });
    expect(vi.mocked(api.addDocumentLink)).not.toHaveBeenCalled();
  });
});
