import { beforeEach, describe, it, expect, vi } from "vitest";
import {
  applyTriage,
  BLANK_FIELDS,
  commitWorld,
  type CommitEntityPatch,
  draftDocTexts,
  persistStatsDiff,
  renderProposalImages,
  toCreatorDoc,
} from "./storylineCreator";
import { blankStat } from "./editor";
import * as api from "@/lib/api";
import type { ProposedWorld, StatDefinition } from "@/lib/types";

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
  it("a fresh doc starts untriaged: Select (uncategorized), RAG on, Draft off", () => {
    const d = toCreatorDoc({ name: "a.md", text: "x" });
    expect(d.category).toBe("select");
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
