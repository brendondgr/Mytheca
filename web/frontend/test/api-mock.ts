import { vi } from "vitest";
import { monoOf } from "@/lib/monogram";
import {
  SEED_CHARACTERS,
  SEED_SCENARIOS,
  SEED_SETTINGS,
  SEED_STORYLINES,
} from "@/lib/seed-data";
import type { Character, Scenario, Setting } from "@/lib/types";

/**
 * A `vi`-mocked `@/lib/api` backed by the Embergate seed, so the Library tests
 * stay meaningful (and async) without a live backend. Use as:
 *
 *   vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());
 */
export function makeApiMock() {
  let n = 0;
  const nid = (prefix: string) => `${prefix}-test-${++n}`;

  return {
    API_BASE: "http://test/api",
    ApiError: class ApiError extends Error {},

    listStorylines: vi.fn(async () =>
      SEED_STORYLINES.map((s) => ({
        id: s.id,
        title: s.title,
        genre: s.genre,
        tagline: s.tagline,
        symbol: s.symbol,
        symbolColor: s.symbolColor,
      })),
    ),
    getStoryline: vi.fn(async (id: string) => {
      const s = SEED_STORYLINES.find((x) => x.id === id) ?? SEED_STORYLINES[0];
      return {
        id,
        title: s.title,
        genre: s.genre,
        tagline: s.tagline,
        premise: s.premise,
        worldPrimer: s.worldPrimer,
        symbol: s.symbol,
        symbolColor: s.symbolColor,
      };
    }),
    createStoryline: vi.fn(
      async (body: {
        title?: string;
        genre?: string;
        tagline?: string;
        premise?: string;
        worldPrimer?: string;
        symbol?: string;
        symbolColor?: string;
      }) => ({
        id: nid("sl"),
        title: body.title ?? "Untitled Storyline",
        genre: body.genre ?? "Uncharted",
        tagline: body.tagline,
        premise: body.premise,
        worldPrimer: body.worldPrimer,
        symbol: body.symbol,
        symbolColor: body.symbolColor,
      }),
    ),
    updateStoryline: vi.fn(
      async (
        id: string,
        body: {
          title?: string;
          genre?: string;
          tagline?: string;
          premise?: string;
          worldPrimer?: string;
          symbol?: string;
          symbolColor?: string;
        },
      ) => ({ id, ...body }),
    ),
    deleteStoryline: vi.fn(async () => {}),

    // ---- agentic storyline editor / creator ----
    storylineAgentEditStream: vi.fn(async function* () {
      yield { type: "message" as const, delta: "Here is a tighter tagline.", done: false };
      yield { type: "message" as const, delta: "", done: true };
      yield {
        type: "plan" as const,
        plan: {
          changes: [{ field: "tagline", after: "Every secret has a price.", rationale: "punchier" }],
          statChanges: [],
          notes: "",
        },
        baseVersion: "hash-1",
      };
    }),
    storylineAgentCreateStream: vi.fn(async function* () {
      yield { type: "message" as const, delta: "Here is a draft.", done: false };
      yield { type: "message" as const, delta: "", done: true };
      yield {
        type: "plan" as const,
        plan: {
          changes: [{ field: "title", after: "Assistant Draft", rationale: "evocative" }],
          statChanges: [],
          notes: "",
        },
      };
    }),
    applyStorylineAgentPlan: vi.fn(async (id: string, body: { plan: { changes: unknown[] } }) => ({
      storyline: { id, title: "Embergate", genre: "Maritime", tagline: "Every secret has a price." },
      applied: body.plan.changes.map(() => "Updated tagline"),
    })),

    // ---- storyline authoring (the creation-time agent) ----
    generateWorldPrimer: vi.fn(async () => ({
      worldPrimer: "A generated, agent-facing primer.\n\nThree powers govern the world.",
    })),

    // ---- triage (the New Storyline page) ----
    triageDocuments: vi.fn(async (docs: { name: string; text: string }[]) => ({
      items: docs.map((d, i) => ({
        name: d.name,
        category: (["character", "setting", "other"] as const)[i % 3],
        includeDraft: i % 3 === 2,
        includeRag: true,
        includeExtract: false,
        rationale: "mocked",
      })),
    })),
    // Live (per-file) triage — one status + item per doc, then done.
    triageDocumentsStream: vi.fn(async function* (docs: { name: string; text: string }[]) {
      for (let i = 0; i < docs.length; i++) {
        yield { type: "status" as const, name: docs[i].name, index: i, total: docs.length };
        yield {
          type: "item" as const,
          item: {
            name: docs[i].name,
            category: (["character", "setting", "other"] as const)[i % 3],
            includeDraft: i % 3 === 2,
            includeRag: true,
            includeExtract: false,
            rationale: "mocked",
          },
        };
      }
      yield { type: "done" as const };
    }),

    // World population — the create-time cast + settings build. Streams the same
    // sequenced frames the backend does: a plan, then one `entity` per persisted row.
    populateWorldStream: vi.fn(async function* (
      _storylineId: string,
      body: { withArtwork?: boolean; fromSeq?: number } = {},
    ) {
      let seq = -1;
      const next = <T extends object>(frame: T) => ({ seq: ++seq, ...frame });
      const named = (name: string, docName: string) => ({
        name,
        seed: "",
        source: `${name} is described in ${docName}.`,
        docId: `cd-${name}`,
        docName,
      });
      yield next({ type: "status" as const, stage: "roster" as const, message: "Planning…", name: "", index: 0, total: 0 });
      yield next({
        type: "plan" as const,
        source: "documents" as const,
        characters: [named("Maerin Voss", "maerin.md"), named("Harbormaster Cael", "cael.md")],
        settings: [named("The Salt Wharf", "wharf.md")],
        note: "Built from 3 of your files.",
      });
      for (const [i, name] of ["Maerin Voss", "Harbormaster Cael"].entries()) {
        yield next({ type: "status" as const, stage: "character" as const, message: `Writing ${name}…`, name, index: i + 1, total: 2 });
        yield next({ type: "status" as const, stage: "character" as const, message: `Finding ${name}'s voice…`, name, index: i + 1, total: 2 });
        yield next({
          type: "entity" as const,
          stage: "character" as const,
          id: nid("c"),
          name,
          role: "Smuggler",
          image: body.withArtwork ? "/media/portraits/mock.webp" : null,
        });
      }
      yield next({ type: "status" as const, stage: "setting" as const, message: "Building The Salt Wharf…", name: "The Salt Wharf", index: 1, total: 1 });
      yield next({
        type: "entity" as const,
        stage: "setting" as const,
        id: nid("s"),
        name: "The Salt Wharf",
        role: "Social Hub",
        image: body.withArtwork ? "/media/scenes/mock.webp" : null,
      });
      yield next({ type: "done" as const, characters: 2, settings: 1 });
    }),

    // ---- context documents (the persisted triaged RAG corpus) ----
    listContextDocuments: vi.fn(async () => [] as unknown[]),
    bulkCreateContextDocuments: vi.fn(
      async (storylineId: string, docs: Record<string, unknown>[]) =>
        docs.map((body, i) => ({
          id: nid("cd"),
          storylineId,
          name: "doc.md",
          content: "",
          category: "other",
          includeDraft: false,
          includeRag: true,
          includeExtract: false,
          source: "upload",
          charCount: 0,
          ...body,
          position: i,
        })),
    ),
    createContextDocument: vi.fn(async (storylineId: string, body: Record<string, unknown>) => ({
      id: nid("cd"),
      storylineId,
      name: "doc.md",
      content: "",
      category: "other",
      includeDraft: false,
      includeRag: true,
      includeExtract: false,
      source: "upload",
      charCount: 0,
      ...body,
    })),
    updateContextDocument: vi.fn(async (docId: string, body: Record<string, unknown>) => ({
      id: docId,
      ...body,
    })),
    deleteContextDocument: vi.fn(async () => {}),
    addDocumentLink: vi.fn(
      async (docId: string, link: { entityType: string; entityId: string }) => ({
        id: docId,
        storylineId: "embergate",
        name: "doc.md",
        content: "",
        category: "other",
        includeDraft: false,
        includeRag: true,
        includeExtract: false,
        source: "upload",
        charCount: 0,
        links: [{ id: nid("cdl"), ...link }],
      }),
    ),
    removeDocumentLink: vi.fn(
      async (docId: string) => ({
        id: docId,
        storylineId: "embergate",
        name: "doc.md",
        content: "",
        category: "other",
        includeDraft: false,
        includeRag: true,
        includeExtract: false,
        source: "upload",
        charCount: 0,
        links: [],
      }),
    ),
    getRagStatus: vi.fn(async () => ({ available: false, indexed: 0 })),
    reindexCorpusStream: vi.fn(async function* () {
      yield { stage: "done", indexed: 0, skipped: 0, total: 0, available: false };
    }),

    listCharacters: vi.fn(async () => SEED_CHARACTERS),
    listSettings: vi.fn(async () => SEED_SETTINGS),
    listScenarios: vi.fn(async () => SEED_SCENARIOS),

    createCharacter: vi.fn(async (storylineId: string, body: Omit<Character, "id" | "mono">) => ({
      id: nid("c"),
      mono: monoOf(body.name),
      ...body,
    })),
    updateCharacter: vi.fn(async (id: string, body: Partial<Character>) => ({
      id,
      mono: monoOf(body.name ?? ""),
      ...body,
    })),
    deleteCharacter: vi.fn(async () => {}),
    setCharacterStats: vi.fn(async (_id: string, values: Record<string, number>) => values),
    getCharacterStats: vi.fn(async (_id: string) => ({}) as Record<string, number>),

    // ---- stat definitions (universal storyline stats) ----
    listStatDefinitions: vi.fn(async () => [] as unknown[]),
    createStatDefinition: vi.fn(async (_storylineId: string, body: Record<string, unknown>) => ({
      description: "",
      visibility: "public",
      guidance: null,
      appliesTo: ["character"],
      bands: [],
      ...body,
    })),
    updateStatDefinition: vi.fn(
      async (_storylineId: string, key: string, body: Record<string, unknown>) => ({ key, ...body }),
    ),
    deleteStatDefinition: vi.fn(async () => {}),

    // ---- character authoring (the agentic Character Creator) ----
    draftCharacter: vi.fn(async (seed: string) => ({
      name: "Drafted Hero",
      role: "Drafted Role",
      traits: "Bold · Wry · Loyal",
      speech: `Speaks of: ${seed}`,
      goal: "A drafted goal.",
      secret: "A drafted secret.",
      appearance: "A drafted appearance.",
      background: "A drafted background.",
      personality: "A drafted personality.",
      color: "#2F7D6B",
    })),
    generatePortraitPrompts: vi.fn(async () => ({
      positive: "young human hero, watercolor portrait, soft washes",
      negative: "blurry, text, watermark",
    })),
    generatePortrait: vi.fn(async () => ({ portrait: "/media/portraits/test.webp" })),
    proposeVoiceSamples: vi.fn(async () => ({
      samples: [
        { situation: "greeted warmly", sample: "State your business." },
        { situation: "offered a bribe", sample: "Coin talks. I decide what it says." },
      ],
    })),
    proposeStartingStats: vi.fn(async () => ({
      proposals: [
        { key: "health", displayName: "Health", value: 90, min: 0, max: 100, rationale: "hardy" },
        { key: "trust", displayName: "Trust", value: 1, min: -5, max: 5, rationale: "guarded" },
      ],
    })),
    mediaUrl: (path: string) => (path ? `http://test${path}` : path),

    getScenarioRelationships: vi.fn(async () => ({ relationships: [] })),

    // ---- persisted scenes (resume + save-on-close + export) ----
    listPlaySessions: vi.fn(async () => ({ sessions: [] })),
    getSessionHistory: vi.fn(async (_scenarioId: string, sessionId: string) => ({
      session: {
        id: sessionId,
        scenarioId: "sc",
        createdAt: "t",
        updatedAt: "t",
        closedAt: null,
        turnCount: 0,
        preview: "",
      },
      events: [],
      traces: [],
    })),
    closePlaySession: vi.fn(() => {}),
    exportSessionUrl: (scenarioId: string, sessionId: string, format: string) =>
      `http://test/api/play/${scenarioId}/sessions/${sessionId}/export?format=${format}`,

    createSetting: vi.fn(async (storylineId: string, body: Omit<Setting, "id">) => ({
      id: nid("s"),
      timeline: [],
      ...body,
    })),
    updateSetting: vi.fn(async (id: string, body: Partial<Setting>) => ({ id, ...body })),
    deleteSetting: vi.fn(async () => {}),

    // ---- setting authoring (the agentic Setting Creator) ----
    draftSetting: vi.fn(async (seed: string) => ({
      name: "Drafted Place",
      type: "Black Market",
      desc: `A place of: ${seed}`,
      atmosphere: "A drafted atmosphere.",
      features: "Drafted features.",
      currentState: "A drafted current state.",
    })),
    generateSceneArtPrompts: vi.fn(async () => ({
      positive: "fog-bound harbor at dawn, watercolor, establishing shot, no people",
      negative: "people, text, watermark",
    })),
    generateSceneArt: vi.fn(async () => ({ image: "/media/scenes/test.webp" })),

    draftScenario: vi.fn(async (seed: string) => ({
      title: "Drafted Scene",
      genre: "Intrigue",
      tone: "Tension · rising",
      goal: `At stake: ${seed}`,
      opening: "A drafted opening beat.",
      castIds: ["c-maerin", "c-doran"],
      settingId: "s-harbor",
    })),

    createScenario: vi.fn(async (storylineId: string, body: Omit<Scenario, "id">) => ({
      id: nid("sc"),
      ...body,
    })),
    updateScenario: vi.fn(async (id: string, body: Partial<Scenario>) => ({ id, ...body })),
    deleteScenario: vi.fn(async () => {}),

    // ---- options / settings ----
    getSettings: vi.fn(async () => ({
      llm: {
        baseUrl: "",
        model: "",
        provider: "openai-compatible",
        params: {
          temperature: 0.7,
          maxTokens: 512,
          topP: 1,
          frequencyPenalty: 0,
          presencePenalty: 0,
        },
        hasApiKey: false,
        apiKeyHint: null,
        authoringConcurrency: 3,
        maxContextTokens: 16384,
      },
      library: { defaultStorylineId: null, openLastStoryline: true },
      comfy: {
        baseUrl: "http://localhost:8199",
        workflow: "ZiT-Workflow.json",
        params: { steps: 4, cfg: 1, width: 1024, height: 1024, batchSize: 1, negativePrompt: "" },
      },
      prompts: {
        catalog: [
          {
            key: "narrator.system",
            agent: "Narrator",
            label: "Transition beat",
            description: "Short narration between beats.",
            default: "DEFAULT narrator system prompt.",
          },
          {
            key: "planner.system",
            agent: "Planner",
            label: "Next-beat loop",
            description: "Decides the next beat.",
            default: "DEFAULT planner system prompt.",
          },
        ],
        overrides: {},
      },
    })),
    updatePromptsConfig: vi.fn(async (body: { overrides: Record<string, string> }) => ({
      catalog: [
        {
          key: "narrator.system",
          agent: "Narrator",
          label: "Transition beat",
          description: "Short narration between beats.",
          default: "DEFAULT narrator system prompt.",
        },
        {
          key: "planner.system",
          agent: "Planner",
          label: "Next-beat loop",
          description: "Decides the next beat.",
          default: "DEFAULT planner system prompt.",
        },
      ],
      overrides: Object.fromEntries(
        Object.entries(body.overrides).filter(([, v]) => v.trim()),
      ),
    })),
    updateLlmConfig: vi.fn(async (body: Record<string, unknown>) => ({
      baseUrl: "",
      model: "",
      provider: "openai-compatible",
      params: {
        temperature: 0.7,
        maxTokens: 512,
        topP: 1,
        frequencyPenalty: 0,
        presencePenalty: 0,
      },
      hasApiKey: false,
      apiKeyHint: null,
      authoringConcurrency: 3,
      maxContextTokens: 16384,
      ...body,
    })),
    getLlmContextWindow: vi.fn(async () => ({
      maxContextTokens: 16384,
      source: "configured" as const,
    })),
    updateLibraryDefaults: vi.fn(async (body: Record<string, unknown>) => ({
      defaultStorylineId: null,
      openLastStoryline: true,
      ...body,
    })),
    fetchLlmModels: vi.fn(async () => ({ models: ["llama-3.1-8b", "qwen2.5"] })),
    testLlmConnection: vi.fn(async (body: { model: string }) => ({
      ok: true,
      model: body.model,
      latencyMs: 42,
      sample: "ok",
    })),

    // ---- ComfyUI image generation ----
    updateComfyConfig: vi.fn(async (body: Record<string, unknown>) => ({
      baseUrl: "http://localhost:8199",
      workflow: "ZiT-Workflow.json",
      params: { steps: 4, cfg: 1, width: 1024, height: 1024, batchSize: 1, negativePrompt: "" },
      ...body,
    })),
    fetchComfyWorkflows: vi.fn(async () => ({ workflows: ["ZiT-Workflow.json", "Other.json"] })),
    checkComfyStatus: vi.fn(async () => ({
      ok: true,
      comfyuiVersion: "0.25.0",
      device: "AMD Radeon",
      pythonVersion: "3.13.11",
    })),

    getHealth: vi.fn(async () => ({ status: "ok" })),
    getLlmBackend: vi.fn(async () => ({
      backend: "vllm",
      budgets: { low: 256, medium: 512, high: 1024, very_high: 2048, max: 4096 },
    })),

    // ---- Orphaned-media cleanup ----
    getMediaOrphans: vi.fn(async () => ({
      portraits: { orphanCount: 3, eligibleCount: 2, totalBytes: 30720, eligibleBytes: 20480 },
      scenes: { orphanCount: 1, eligibleCount: 1, totalBytes: 10240, eligibleBytes: 10240 },
      orphanCount: 4,
      eligibleCount: 3,
      totalBytes: 40960,
      eligibleBytes: 30720,
      minAgeHours: 24,
    })),
    cleanupMediaOrphans: vi.fn(async () => ({
      deletedCount: 3,
      freedBytes: 30720,
      skippedRecentCount: 1,
    })),

    // ---- Story Graph (Neo4j substrate) ----
    getScenarioGraph: vi.fn(async (scenarioId: string) => ({
      available: false,
      scenarioId,
      nodes: [],
      edges: [],
    })),
    listGraphTypes: vi.fn(async () => [
      {
        id: "gt-character",
        storylineId: null,
        kind: "node",
        typeName: "Character",
        fieldSchema: [],
        description: "The anchor node.",
        valence: null,
        decay: null,
        status: "built_in",
      },
    ]),
    createGraphType: vi.fn(async (storylineId: string, body: Record<string, unknown>) => ({
      id: nid("gt"),
      storylineId,
      fieldSchema: [],
      description: "",
      valence: null,
      decay: null,
      status: "experimental",
      ...body,
    })),
    updateGraphType: vi.fn(async (typeId: string, body: Record<string, unknown>) => ({
      id: typeId,
      storylineId: "embergate",
      kind: "node",
      typeName: "Ritual",
      fieldSchema: [],
      description: "",
      valence: null,
      decay: null,
      status: "experimental",
      ...body,
    })),
    deleteGraphType: vi.fn(async () => {}),
  };
}
