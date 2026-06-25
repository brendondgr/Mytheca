// Typed client for the Velora FastAPI backend (docs/api-contract.md).
//
// Response/input types reuse the domain types in `@/lib/types` so the wire shape and
// the UI model stay in lockstep. When `web/shared/contracts/` is populated these
// should re-export from there. Errors surface as `ApiError` carrying the backend
// envelope `{ error: { code, message, details } }`.

import type { Character, Scenario, Setting, Storyline } from "@/lib/types";

/** Backend base URL. Configurable via NEXT_PUBLIC_API_URL (see .env.example). */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:3345/api";

/** A storyline as returned by the list/CRUD endpoints — summary, no children. */
export type StorylineSummary = Omit<
  Storyline,
  "characters" | "settings" | "scenarios"
>;

export type StorylineInput = Partial<Omit<Storyline, "characters" | "settings" | "scenarios">>;
/** Create payload: the backend derives `mono` from `name` and generates `id`. */
export type CharacterInput = Omit<Character, "id" | "mono"> & { mono?: string };
export type SettingInput = Omit<Setting, "id">;
export type ScenarioInput = Omit<Scenario, "id">;

interface ApiErrorBody {
  error?: { code?: string; message?: string; details?: unknown };
}

/** Error thrown for any non-2xx response (or a network failure). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { headers, ...rest } = init ?? {};
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...headers },
      ...rest,
    });
  } catch (cause) {
    throw new ApiError(0, "network_error", "Could not reach the server.", cause);
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  const body = text ? (JSON.parse(text) as unknown) : undefined;

  if (!res.ok) {
    const err = (body as ApiErrorBody | undefined)?.error;
    throw new ApiError(
      res.status,
      err?.code ?? "error",
      err?.message ?? res.statusText,
      err?.details,
    );
  }
  return body as T;
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });
const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const put = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });
const del = (path: string) => request<void>(path, { method: "DELETE" });

/** Resolve a relative `/media/...` URL (portraits) against the API origin. */
export function mediaUrl(path: string): string {
  if (!path) return path;
  if (/^https?:\/\//.test(path)) return path;
  const origin = API_BASE.replace(/\/api\/?$/, "");
  return `${origin}${path.startsWith("/") ? "" : "/"}${path}`;
}

// ---- storylines ----
export const listStorylines = () => request<StorylineSummary[]>("/storylines");
export const createStoryline = (body: StorylineInput) =>
  post<StorylineSummary>("/storylines", body);
export const updateStoryline = (id: string, body: StorylineInput) =>
  patch<StorylineSummary>(`/storylines/${id}`, body);
export const deleteStoryline = (id: string) => del(`/storylines/${id}`);

// ---- storyline authoring (the creation-time agent process) ----
// `docsOverview` is inline text read from dropped reference files in the browser,
// used to ground a single generation only — never uploaded/persisted (no RAG).

/** Metadata drafted from a one-sentence seed (fills the create form). */
export interface StorylineDraftResult {
  title: string;
  genre: string;
  tagline: string;
  premise: string;
}

export interface WorldPrimerResult {
  worldPrimer: string;
}

export const draftStoryline = (seed: string, docsOverview?: string) =>
  post<StorylineDraftResult>("/storylines/draft", { seed, docsOverview });

export const generateWorldPrimer = (body: {
  premise?: string;
  seed?: string;
  docsOverview?: string;
}) => post<WorldPrimerResult>("/storylines/primer", body);

// ---- per-storyline children ----
export const listCharacters = (storylineId: string) =>
  request<Character[]>(`/storylines/${storylineId}/characters`);
export const listSettings = (storylineId: string) =>
  request<Setting[]>(`/storylines/${storylineId}/settings`);
export const listScenarios = (storylineId: string) =>
  request<Scenario[]>(`/storylines/${storylineId}/scenarios`);

// ---- characters ----
export const createCharacter = (storylineId: string, body: CharacterInput) =>
  post<Character>(`/storylines/${storylineId}/characters`, body);
export const updateCharacter = (id: string, body: Partial<CharacterInput>) =>
  patch<Character>(`/characters/${id}`, body);
export const deleteCharacter = (id: string) => del(`/characters/${id}`);

/** Replace a character's stat values (clamped server-side). Map of {key: value}. */
export const setCharacterStats = (id: string, values: Record<string, number>) =>
  put<Record<string, number>>(`/characters/${id}/stats`, values);

// ---- character authoring (the agentic Character Creator) ----
// Produces a character's base identity only (§1 node properties) — no graph.
// `docsOverview` is inline dropped-file text used to ground one generation (no RAG).

/** A character drafted from a seed (fills the create form). */
export interface CharacterDraftResult {
  name: string;
  role: string;
  traits: string;
  speech: string;
  goal: string;
  secret: string;
  appearance: string;
  background: string;
  personality: string;
  color: string;
}

export interface PortraitPromptResult {
  positive: string;
  negative: string;
}

export interface PortraitResult {
  /** Relative `/media/...` URL of the saved WebP portrait. */
  portrait: string;
}

export interface StartingStatProposal {
  key: string;
  displayName: string;
  value: number;
  min: number;
  max: number;
  rationale: string;
}

export interface StartingStatsResult {
  proposals: StartingStatProposal[];
}

export const draftCharacter = (seed: string, docsOverview?: string, storylineId?: string) =>
  post<CharacterDraftResult>("/characters/draft", { seed, docsOverview, storylineId });

export const generatePortraitPrompts = (body: {
  name?: string;
  role?: string | null;
  appearance?: string | null;
  traits?: string | null;
  personality?: string | null;
  species?: string | null;
  notes?: string | null;
}) => post<PortraitPromptResult>("/characters/portrait-prompts", body);

export const generatePortrait = (body: {
  positive: string;
  negative?: string;
  baseUrl?: string;
  workflow?: string;
  width?: number;
  height?: number;
  steps?: number;
  cfg?: number;
}) => post<PortraitResult>("/characters/portrait", body);

export const proposeStartingStats = (body: {
  storylineId: string;
  name?: string;
  role?: string | null;
  traits?: string | null;
  personality?: string | null;
  background?: string | null;
}) => post<StartingStatsResult>("/characters/starting-stats", body);

// ---- settings ----
export const createSetting = (storylineId: string, body: SettingInput) =>
  post<Setting>(`/storylines/${storylineId}/settings`, body);
export const updateSetting = (id: string, body: Partial<SettingInput>) =>
  patch<Setting>(`/settings/${id}`, body);
export const deleteSetting = (id: string) => del(`/settings/${id}`);

// ---- scenarios ----
export const createScenario = (storylineId: string, body: ScenarioInput) =>
  post<Scenario>(`/storylines/${storylineId}/scenarios`, body);
export const updateScenario = (id: string, body: Partial<ScenarioInput>) =>
  patch<Scenario>(`/scenarios/${id}`, body);
export const deleteScenario = (id: string) => del(`/scenarios/${id}`);

// ---- options / settings ----
// Mirrors web/backend/app/schemas/settings.py. The LLM API key is write-only:
// reads expose only `hasApiKey` + a masked `apiKeyHint`.

export interface LlmParams {
  temperature: number;
  maxTokens: number;
  topP: number;
  frequencyPenalty: number;
  presencePenalty: number;
}

export interface LlmConfig {
  baseUrl: string;
  model: string;
  provider: string;
  params: LlmParams;
  hasApiKey: boolean;
  apiKeyHint: string | null;
}

/** PATCH payload. Omit `apiKey` to keep the stored key; "" clears it. */
export interface LlmConfigUpdate {
  baseUrl?: string;
  model?: string;
  provider?: string;
  params?: LlmParams;
  apiKey?: string;
}

export interface LibraryDefaults {
  defaultStorylineId: string | null;
  openLastStoryline: boolean;
}

export type LibraryDefaultsUpdate = Partial<LibraryDefaults>;

export interface ComfyParams {
  steps: number;
  cfg: number;
  width: number;
  height: number;
  batchSize: number;
  negativePrompt: string;
}

export interface ComfyConfig {
  baseUrl: string;
  workflow: string;
  params: ComfyParams;
}

export type ComfyConfigUpdate = Partial<ComfyConfig>;

export interface ComfyStatusResult {
  ok: boolean;
  comfyuiVersion: string;
  device: string;
  pythonVersion: string;
}

export interface ComfyWorkflowsResult {
  workflows: string[];
}

export interface AppSettings {
  llm: LlmConfig;
  library: LibraryDefaults;
  comfy: ComfyConfig;
}

export interface LlmModelsResult {
  models: string[];
}

export interface LlmTestResult {
  ok: boolean;
  model: string;
  latencyMs: number;
  sample: string;
}

export const getSettings = () => request<AppSettings>("/options");
export const updateLlmConfig = (body: LlmConfigUpdate) =>
  patch<LlmConfig>("/options/llm", body);
export const updateLibraryDefaults = (body: LibraryDefaultsUpdate) =>
  patch<LibraryDefaults>("/options/library", body);
export const fetchLlmModels = (body: { baseUrl?: string; apiKey?: string }) =>
  post<LlmModelsResult>("/options/llm/models", body);
export const testLlmConnection = (body: {
  baseUrl?: string;
  apiKey?: string;
  model: string;
  params?: LlmParams;
}) => post<LlmTestResult>("/options/llm/test", body);

// ---- ComfyUI image generation ----
export const updateComfyConfig = (body: ComfyConfigUpdate) =>
  patch<ComfyConfig>("/options/comfy", body);
export const fetchComfyWorkflows = () =>
  request<ComfyWorkflowsResult>("/options/comfy/workflows");
export const checkComfyStatus = (body: { baseUrl?: string }) =>
  post<ComfyStatusResult>("/options/comfy/status", body);

/** Backend health check. Lives at `/health`, outside the `/api` prefix. */
export async function getHealth(): Promise<{ status: string }> {
  const base = API_BASE.replace(/\/api\/?$/, "");
  try {
    const res = await fetch(`${base}/health`, { credentials: "include" });
    if (!res.ok) throw new ApiError(res.status, "error", res.statusText);
    return (await res.json()) as { status: string };
  } catch (cause) {
    if (cause instanceof ApiError) throw cause;
    throw new ApiError(0, "network_error", "Could not reach the server.", cause);
  }
}
