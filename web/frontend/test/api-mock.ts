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

    // ---- storyline authoring (the creation-time agent) ----
    draftStoryline: vi.fn(async (seed: string) => ({
      title: "Drafted World",
      genre: "Drafted Genre",
      tagline: `Tagline for: ${seed}`,
      premise: "Drafted premise paragraph one.\n\nDrafted premise paragraph two.",
    })),
    generateWorldPrimer: vi.fn(async () => ({
      worldPrimer: "A generated, agent-facing primer.\n\nThree powers govern the world.",
    })),

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
    proposeStartingStats: vi.fn(async () => ({
      proposals: [
        { key: "health", displayName: "Health", value: 90, min: 0, max: 100, rationale: "hardy" },
        { key: "trust", displayName: "Trust", value: 1, min: -5, max: 5, rationale: "guarded" },
      ],
    })),
    mediaUrl: (path: string) => (path ? `http://test${path}` : path),

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
      },
      library: { defaultStorylineId: null, openLastStoryline: true },
      comfy: {
        baseUrl: "http://localhost:8199",
        workflow: "ZiT-Workflow.json",
        params: { steps: 4, cfg: 1, width: 1024, height: 1024, batchSize: 1, negativePrompt: "" },
      },
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
      ...body,
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
  };
}
