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
      SEED_STORYLINES.map((s) => ({ id: s.id, title: s.title, genre: s.genre, tagline: s.tagline })),
    ),
    createStoryline: vi.fn(async (body: { title?: string; genre?: string; tagline?: string }) => ({
      id: nid("sl"),
      title: body.title ?? "Untitled Storyline",
      genre: body.genre ?? "Uncharted",
      tagline: body.tagline,
    })),
    updateStoryline: vi.fn(async (id: string, body: { title?: string; genre?: string; tagline?: string }) => ({
      id,
      ...body,
    })),
    deleteStoryline: vi.fn(async () => {}),

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

    createSetting: vi.fn(async (storylineId: string, body: Omit<Setting, "id">) => ({
      id: nid("s"),
      ...body,
    })),
    updateSetting: vi.fn(async (id: string, body: Partial<Setting>) => ({ id, ...body })),
    deleteSetting: vi.fn(async () => {}),

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
    getHealth: vi.fn(async () => ({ status: "ok" })),
  };
}
