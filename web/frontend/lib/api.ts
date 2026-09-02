// Typed client for the Mytheca FastAPI backend (docs/api-contract.md).
//
// Response/input types reuse the domain types in `@/lib/types` so the wire shape and
// the UI model stay in lockstep. When `web/shared/contracts/` is populated these
// should re-export from there. Errors surface as `ApiError` carrying the backend
// envelope `{ error: { code, message, details } }`.

import type {
  ArtStyleId,
  MomentRequestBody,
  MomentStreamFrame,
  GhostwriteStreamFrame,
  PersistedEvent,
  PresenceStatus,
  BeatMemory,
  SceneKnowledge,
  SessionHistory,
  StandingItem,
  RewindResult,
  SessionSummary,
  TurnRequestBody,
  TurnStreamFrame,
} from "@/lib/events";
import type {
  AgentEditFrame,
  BeatLength,
  AgentMessage,
  Character,
  ContextDocument,
  ContextDocumentIndexEntry,
  DocCategory,
  EntityScope,
  GraphTypeDefinition,
  PopulateEvent,
  RosterSource,
  Scenario,
  ScenarioGraph,
  LlmHealth,
  Setting,
  StatDefinition,
  Storyline,
  StoryPlan,
  StorylineScope,
  TriageEvent,
  TriageItem,
  VoiceSample,
} from "@/lib/types";

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

/**
 * One automatic re-attempt on a *connect-time* failure, for calls that write nothing.
 *
 * A rejected `fetch()` means no response was ever received — the classic case being a
 * pooled keep-alive connection the server closes at the same moment the browser reuses
 * it (RFC 7230 §6.3.1 permits retrying that). Browsers do not retry a POST themselves,
 * because a POST may have been processed. For our generation endpoints it cannot have
 * been: they write nothing, so the worst case of a second attempt is a second
 * generation. Never set `retry` on a CRUD writer — a retried create is a duplicate row.
 */
export interface CallOptions {
  retry?: boolean;
}

/** True for a rejected `fetch()` that the caller did not abort. */
function isConnectFailure(cause: unknown): boolean {
  return !(cause instanceof DOMException && cause.name === "AbortError");
}

/**
 * What a transport failure looked like, attached to the thrown `ApiError.details`
 * and logged once.
 *
 * `elapsedMs` is the diagnostic that matters: the browser reports every transport
 * failure as an opaque `TypeError`, so *how long the request survived* is the only
 * signal that separates the possible causes. Near-zero means the connection was
 * refused or a pooled socket was dead — the server was never reached. Tens of
 * seconds means it was reached, worked, and something cut the connection; a value
 * that repeats at the same number across failures is an idle timeout naming itself.
 */
export interface TransportFailure {
  path: string;
  elapsedMs: number;
  attempts: number;
  cause: string;
  phase: "connect" | "stream";
}

function describe(cause: unknown): string {
  return cause instanceof Error ? `${cause.name}: ${cause.message}` : String(cause);
}

function reportTransportFailure(info: TransportFailure): TransportFailure {
  // Logged, not swallowed: the panel shows a sentence, but diagnosing this needs the
  // timing. One line, only on failure.
  console.warn("[mytheca] request failed", info);
  return info;
}

async function fetchOnce(
  url: string,
  init: RequestInit,
  retry: boolean,
): Promise<{ res: Response; attempts: number }> {
  try {
    return { res: await fetch(url, init), attempts: 1 };
  } catch (cause) {
    if (!retry || !isConnectFailure(cause)) throw cause;
    // Fresh connection; if this fails too the server really is unreachable.
    return { res: await fetch(url, init), attempts: 2 };
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  opts: CallOptions = {},
): Promise<T> {
  const { headers, ...rest } = init ?? {};
  const startedAt = Date.now();
  let res: Response;
  try {
    ({ res } = await fetchOnce(
      `${API_BASE}${path}`,
      {
        credentials: "include",
        headers: { "Content-Type": "application/json", ...headers },
        ...rest,
      },
      Boolean(opts.retry),
    ));
  } catch (cause) {
    throw new ApiError(
      0,
      "network_error",
      "Could not reach the server.",
      reportTransportFailure({
        path,
        elapsedMs: Date.now() - startedAt,
        attempts: opts.retry ? 2 : 1,
        cause: describe(cause),
        phase: "connect",
      }),
    );
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

/**
 * A POST that only *generates* — it persists nothing, so a connect-time failure can be
 * re-attempted on a fresh connection. Use this instead of `post` for LLM-backed
 * authoring calls; never for anything that writes.
 */
const generation = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) }, { retry: true });

/**
 * POST `body` and yield each NDJSON line of the streamed response as a parsed
 * object. The backend streaming endpoints (`/storylines/build/stream`,
 * `/triage/stream`) send `application/x-ndjson` — one JSON event per line — so the
 * UI can render progress live. A non-2xx (pre-stream) response is decoded as the
 * usual error envelope and thrown as `ApiError`; pass an `AbortSignal` to cancel.
 */
export async function* postNdjson<T>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
  opts: CallOptions = {},
): AsyncGenerator<T> {
  const startedAt = Date.now();
  let res: Response;
  try {
    ({ res } = await fetchOnce(
      `${API_BASE}${path}`,
      {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal,
      },
      Boolean(opts.retry),
    ));
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(
      0,
      "network_error",
      "Could not reach the server.",
      reportTransportFailure({
        path,
        elapsedMs: Date.now() - startedAt,
        attempts: opts.retry ? 2 : 1,
        cause: describe(cause),
        phase: "connect",
      }),
    );
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let err: ApiErrorBody["error"];
    try {
      err = (JSON.parse(text) as ApiErrorBody | undefined)?.error;
    } catch {
      err = undefined;
    }
    throw new ApiError(
      res.status,
      err?.code ?? "error",
      err?.message ?? res.statusText,
      err?.details,
    );
  }

  if (!res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      let chunk: ReadableStreamReadResult<Uint8Array>;
      try {
        chunk = await reader.read();
      } catch (cause) {
        // The response *started* — the server accepted the request and was working —
        // and then the connection died. That is a different problem from never
        // reaching the server, and it must not be reported as if the server were
        // down. Retrying here is not safe: we cannot know how far the work got.
        if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
        throw new ApiError(
          0,
          "connection_lost",
          "Lost the connection while the server was still working.",
          reportTransportFailure({
            path,
            elapsedMs: Date.now() - startedAt,
            attempts: 1,
            cause: describe(cause),
            phase: "stream",
          }),
        );
      }
      const { done, value } = chunk;
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let nl: number;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (line) yield JSON.parse(line) as T;
      }
    }
  } finally {
    reader.releaseLock();
  }
  const tail = buf.trim();
  if (tail) yield JSON.parse(tail) as T;
}
const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const put = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });
const del = (path: string) => request<void>(path, { method: "DELETE" });

// ---- play (the turn loop) ----
/**
 * Submit one player turn and stream the resulting story events as NDJSON. The
 * response body *is* the stream (one event per line); the client accumulates
 * delta-streamed prose by event id. Pass an `AbortSignal` to cancel.
 */
export function postTurn(
  scenarioId: string,
  body: TurnRequestBody,
  signal?: AbortSignal,
): AsyncGenerator<TurnStreamFrame> {
  return postNdjson<TurnStreamFrame>(`/play/${scenarioId}/turn`, body, signal);
}

/**
 * Paint the moment the scene is in (the transcript's **Create image** control) and stream
 * the two stages back as NDJSON: `moment_stage` (`prompt` → `render`, the latter repeated
 * as a keep-alive while ComfyUI works), then the persisted `scene_image` event — or a
 * terminal `error` frame. Pass an `AbortSignal` to cancel.
 */
export function postSceneMoment(
  scenarioId: string,
  body: MomentRequestBody,
  signal?: AbortSignal,
): AsyncGenerator<MomentStreamFrame> {
  return postNdjson<MomentStreamFrame>(`/play/${scenarioId}/moment/stream`, body, signal);
}

/** Manually set a character's scene presence (the cast-rail control + its undo). Returns
 * the persisted `character_status_change` in the wire-envelope shape. */
export const setPresence = (
  scenarioId: string,
  body: { sessionId: string; characterId: string; status: PresenceStatus; reason?: string },
) => post<PersistedEvent>(`/play/${scenarioId}/presence`, body);

/** One character↔character relationship from the story graph (P6 live Relationships). */
export interface GraphRelationship {
  source: string;
  sourceName: string;
  type: string;
  target: string;
  targetName: string;
  reason: string;
}

/** The scenario's live relationships (empty when the graph is off — caller keeps its seed). */
/**
 * `graphAvailable` separates "this world has no relationships yet" from "there is no graph
 * on this install" — identical from the list alone, and the difference decides whether the
 * scene's **Ties** control is a real setting or one that would silently do nothing.
 */
export const getScenarioRelationships = (scenarioId: string) =>
  request<{ relationships: GraphRelationship[]; graphAvailable?: boolean }>(
    `/play/${scenarioId}/relationships`,
  );

// ---- persisted scenes (resume + save-on-close + export) ----

/** Every saved play-through of a scenario, most-recently-played first (resume list). */
export const listPlaySessions = (scenarioId: string) =>
  request<{ sessions: SessionSummary[] }>(`/play/${scenarioId}/sessions`);

/** The full record of one play-through (events + traces) — replayed to rehydrate the player. */
export const getSessionHistory = (scenarioId: string, sessionId: string) =>
  request<SessionHistory>(`/play/${scenarioId}/sessions/${sessionId}`);

/**
 * "Tell me what happened" — prose describing the scene up to `throughSeq`.
 *
 * Server-side because it is a model call, and it must be the **same** call compaction makes:
 * two summarisers would drift apart in tone and in what each counts as a fact worth keeping.
 */
export const postSessionRecap = (
  scenarioId: string,
  sessionId: string,
  throughSeq?: number | null,
) =>
  request<{ text: string }>(`/play/${scenarioId}/sessions/${sessionId}/recap`, {
    method: "POST",
    body: JSON.stringify({ throughSeq: throughSeq ?? null }),
  });

/**
 * Is the configured model endpoint actually usable right now?
 *
 * Cheap and cached server-side, so the header can poll it — the alternative is a player
 * learning their endpoint died by sending a turn and waiting out the five-minute generation
 * timeout.
 */
export const getLlmHealth = () => request<LlmHealth>("/options/llm/health");

/**
 * What the scene knows right now — the player-facing read of the last turn's context.
 *
 * A plain GET rather than something folded off the stream, because the question is most
 * worth asking on a scene the player has just come back to.
 */
export const getSceneKnowledge = (scenarioId: string, sessionId: string) =>
  request<SceneKnowledge>(`/play/${scenarioId}/sessions/${sessionId}/context`);

/**
 * The memories behind one beat.
 *
 * Fetched on demand rather than carried in transcript state: a transcript holds dozens of
 * beats and the player asks about one of them at a time, so resolving every beat's
 * provenance up front would be work done for a question nobody asked. A beat with nothing
 * behind it answers with an empty list, not an error.
 */
export const getBeatMemory = (scenarioId: string, sessionId: string, eventId: string) =>
  request<BeatMemory>(
    `/play/${scenarioId}/sessions/${sessionId}/beats/${eventId}/memory`,
  );

/**
 * Stop asking for some (or all) of what the scene still owes.
 *
 * A direction now outlives the turn it rode in on — but a debt the player cannot cancel is a
 * bug, not a feature. `itemIds` drops the named entries; `null` clears everything.
 */
export const clearStandingDirection = (
  scenarioId: string,
  sessionId: string,
  itemIds: string[] | null,
) =>
  request<{ standingDirection: StandingItem[] }>(
    `/play/${scenarioId}/sessions/${sessionId}/standing-direction`,
    { method: "POST", body: JSON.stringify({ itemIds }) },
  );

/**
 * Start a **fresh** play-through. Deliberately never touches the existing ones: before this
 * existed the client resumed the most recent session unconditionally, so a scenario could
 * only ever hold one story.
 */
export const createPlaySession = (scenarioId: string, name?: string) =>
  post<SessionSummary>(`/play/${scenarioId}/sessions`, { name: name ?? null });

/** Relabel a play-through. A blank name clears the label and restores the `preview` fallback. */
export const renamePlaySession = (scenarioId: string, sessionId: string, name: string | null) =>
  patch<SessionSummary>(`/play/${scenarioId}/sessions/${sessionId}`, { name });

/**
 * Fork a play-through at a beat into a new one. The original is untouched — that is the
 * whole point, and it is why branch is safe to offer on every beat.
 */
export const branchPlaySession = (
  scenarioId: string,
  sessionId: string,
  body: { atEventId: string; name?: string; expectedSeq?: number },
) => post<SessionSummary>(`/play/${scenarioId}/sessions/${sessionId}/branch`, body);

/**
 * Cut a play-through back to a beat. The whole turn containing that beat goes, with
 * everything after it; the removed history is kept as its own play-through unless
 * `keepSnapshot` is false, and the player's line comes back in `restoredTurn`.
 */
export const rewindPlaySession = (
  scenarioId: string,
  sessionId: string,
  body: { atEventId: string; keepSnapshot?: boolean; expectedSeq?: number },
) => post<RewindResult>(`/play/${scenarioId}/sessions/${sessionId}/rewind`, body);

/**
 * Rewrite one beat's prose — a character's line, the narration, or the player's own. The
 * server rebuilds the recent-turn buffer, so the cast reads the new wording on the next turn
 * rather than the old one out of Redis.
 */
export const editBeat = (
  scenarioId: string,
  sessionId: string,
  eventId: string,
  body: { text: string; expectedSeq?: number },
) => patch<PersistedEvent>(`/play/${scenarioId}/sessions/${sessionId}/beats/${eventId}`, body);

/**
 * Generate another version of a beat, streaming it back as NDJSON. `scope: "beat"` re-runs
 * that beat alone in place; `scope: "turn"` replays the whole turn it belongs to.
 */
export function rerollBeat(
  scenarioId: string,
  sessionId: string,
  eventId: string,
  body: { scope: "beat" | "turn"; expectedSeq?: number },
  signal?: AbortSignal,
): AsyncGenerator<TurnStreamFrame> {
  return postNdjson<TurnStreamFrame>(
    `/play/${scenarioId}/sessions/${sessionId}/beats/${eventId}/reroll`,
    body,
    signal,
  );
}

/** Show one of a beat's kept versions. The server rebuilds the buffer to match. */
export const selectBeatTake = (
  scenarioId: string,
  sessionId: string,
  eventId: string,
  take: number,
) =>
  patch<PersistedEvent>(
    `/play/${scenarioId}/sessions/${sessionId}/beats/${eventId}/take`,
    { take },
  );

/**
 * Draft the player's own line from a note about what they want it to do, streamed as NDJSON.
 * Persists nothing — the draft becomes part of the story only if the player sends it.
 */
export function postGhostwrite(
  scenarioId: string,
  body: {
    sessionId: string;
    intent: string;
    povCharacterId?: string | null;
    mode?: "character" | "narrator";
  },
  signal?: AbortSignal,
): AsyncGenerator<GhostwriteStreamFrame> {
  return postNdjson<GhostwriteStreamFrame>(`/play/${scenarioId}/ghostwrite/stream`, body, signal);
}

/** Delete a play-through and its history (events + traces cascade server-side). */
export const deletePlaySession = (scenarioId: string, sessionId: string) =>
  del(`/play/${scenarioId}/sessions/${sessionId}`);

/**
 * The save-on-close signal: mark a play-through closed. Fire-and-forget, and safe to call
 * during page unload — uses `navigator.sendBeacon` when available so the request survives
 * the navigation (every turn is already persisted; this only stamps recency/close).
 */
export function closePlaySession(scenarioId: string, sessionId: string): void {
  const url = `${API_BASE}/play/${scenarioId}/sessions/${sessionId}/close`;
  if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
    navigator.sendBeacon(url);
    return;
  }
  void fetch(url, { method: "POST", keepalive: true }).catch(() => {});
}

/** URL to download a session's full conversation record (JSON or Markdown). */
export const exportSessionUrl = (
  scenarioId: string,
  sessionId: string,
  format: "json" | "md",
) => `${API_BASE}/play/${scenarioId}/sessions/${sessionId}/export?format=${format}`;

/** Resolve a relative `/media/...` URL (portraits) against the API origin. */
export function mediaUrl(path: string): string {
  if (!path) return path;
  if (/^https?:\/\//.test(path)) return path;
  const origin = API_BASE.replace(/\/api\/?$/, "");
  return `${origin}${path.startsWith("/") ? "" : "/"}${path}`;
}

// ---- storylines ----
export const listStorylines = () => request<StorylineSummary[]>("/storylines");
export const getStoryline = (id: string) => request<StorylineSummary>(`/storylines/${id}`);
export const createStoryline = (body: StorylineInput) =>
  post<StorylineSummary>("/storylines", body);
export const updateStoryline = (id: string, body: StorylineInput) =>
  patch<StorylineSummary>(`/storylines/${id}`, body);
export const deleteStoryline = (id: string) => del(`/storylines/${id}`);

// ---- agentic storyline editor / creator (conversational, plan → implement) ----
// The author sets a write scope, chats with the agent (in-chat memory), and the
// agent streams a reply + an optional structured plan. Approval applies the plan
// (edit) or fills the create form. See docs/api-contract.md.

/** The author's current form values — the agent's read context + plan before-values. */
export interface StorylineFieldsSnapshot {
  title?: string;
  genre?: string;
  tagline?: string;
  premise?: string;
  worldPrimer?: string;
  stats?: StatDefinition[];
  /** The narrative style guide as it stands in the editor ({block id → text}). */
  styleBlocks?: Record<string, string>;
}

export interface StorylineAgentBody {
  scope: StorylineScope;
  messages: AgentMessage[];
  fields: StorylineFieldsSnapshot;
  /**
   * Inline text of the context files the author kept selected for **Draft**, read in
   * the browser and concatenated by `concatDocs` (capped at `DOCS_CHAR_CAP`). It
   * grounds this turn only — the corpus is persisted separately on commit. Omit it
   * and the assistant reasons from the form fields alone.
   */
  docsOverview?: string;
}

/** Converse with the storyline **editor** agent for an existing world (NDJSON). */
export const storylineAgentEditStream = (
  id: string,
  body: StorylineAgentBody,
  signal?: AbortSignal,
) =>
  // No writes on this path (approval is a separate POST), so a connect-time failure
  // is safe to re-attempt on a fresh connection.
  postNdjson<AgentEditFrame>(`/storylines/${id}/agent/edit/stream`, body, signal, {
    retry: true,
  });

/** Converse with the storyline **creation** agent from a blank/partial start (NDJSON). */
export const storylineAgentCreateStream = (body: StorylineAgentBody, signal?: AbortSignal) =>
  postNdjson<AgentEditFrame>(`/storylines/agent/create/stream`, body, signal, { retry: true });

export interface StorylineApplyBody {
  scope: StorylineScope;
  plan: StoryPlan;
  baseVersion?: string | null;
}

export interface StorylineApplyResult {
  storyline: StorylineSummary;
  applied: string[];
}

/** Approve → implement an edit plan against an existing storyline. */
export const applyStorylineAgentPlan = (id: string, body: StorylineApplyBody) =>
  post<StorylineApplyResult>(`/storylines/${id}/agent/apply`, body);

// ---- storyline authoring (the creation-time agent process) ----
// `docsOverview` is inline text read from dropped reference files in the browser,
// used to ground a single generation only — never uploaded/persisted (no RAG).

export interface WorldPrimerResult {
  worldPrimer: string;
}

export const generateWorldPrimer = (body: {
  premise?: string;
  seed?: string;
  docsOverview?: string;
}) => generation<WorldPrimerResult>("/storylines/primer", body);

/**
 * The drafted narrative style guide, as block TEXT.
 *
 * The agent may answer with a preset id instead of writing one; the backend resolves that
 * to the preset's text, so the client never has to know which path ran and the author edits
 * their own copy either way. `{}` means "no style" — an ordinary outcome, not a failure.
 */
export interface StyleGuideDraftResult {
  styleBlocks: Record<string, string>;
}

export const generateStyleGuide = (body: {
  premise?: string;
  seed?: string;
  docsOverview?: string;
}) => generation<StyleGuideDraftResult>("/storylines/style", body);

/**
 * Revise the guide the author is looking at, on their instruction.
 *
 * Returns the COMPLETE revised guide, so a block the agent left out is one it removed. An
 * empty `styleBlocks` means **leave it alone** — never "clear the guide", which is the one
 * outcome an author cannot undo.
 */
export const reviseStyleGuide = (body: {
  instruction: string;
  current: Record<string, string>;
  premise?: string;
}) => generation<StyleGuideDraftResult>("/storylines/style/revise", body);

// ---- triage (the New Storyline page) ----
// Triage classifies dropped docs into Characters/Settings/Other + Draft/RAG. It does
// not persist — the page commits the triaged corpus via CRUD.

export interface TriageResult {
  items: TriageItem[];
}

export const triageDocuments = (
  docs: { name: string; text: string }[],
  storylineId?: string,
) => generation<TriageResult>("/storylines/triage", { docs, storylineId });

/** Live (per-file) triage — yields a `status` + `item` per doc, then `done`. */
export const triageDocumentsStream = (
  docs: { name: string; text: string }[],
  storylineId?: string,
  signal?: AbortSignal,
) =>
  postNdjson<TriageEvent>("/storylines/triage/stream", { docs, storylineId }, signal, {
    retry: true,
  });

// ---- world population (the New Storyline page's build step) ----
// Fills a freshly-created world with a generated cast + settings. Run AFTER the
// storyline, its stats, and its corpus are persisted — the roster is grounded in
// the saved world, and the entities are written straight to it.

export interface PopulateWorldBody {
  docsOverview?: string;
  source?: RosterSource;
  maxCharacters?: number;
  maxSettings?: number;
  withArtwork?: boolean;
  /** The look every image in the build wears; omitted uses the Options default. */
  artStyle?: ArtStyleId;
  /** Re-attach to a run already in flight and replay from this frame onward. */
  fromSeq?: number;
}

/** Stream a world's population — `status` / `entity` / `error` frames, then `done`. */
export const populateWorldStream = (
  storylineId: string,
  body: PopulateWorldBody = {},
  signal?: AbortSignal,
) =>
  postNdjson<PopulateEvent>(`/storylines/${storylineId}/populate/stream`, body, signal, {
    retry: true,
  });

// ---- context documents (the persisted RAG corpus) ----
export type ContextDocumentInput = {
  name: string;
  content?: string;
  category?: DocCategory;
  includeDraft?: boolean;
  includeRag?: boolean;
  /** Opt-in: mine this doc for named characters/settings during the world build. */
  includeExtract?: boolean;
  source?: string;
  /** Optional entity scope (character/setting/scenario); null = storyline-level. */
  entityType?: "character" | "setting" | "scenario" | null;
  entityId?: string | null;
};

/**
 * List a world's context docs. Pass `{ entityType, entityId }` to get just one
 * entity's OWNED files (they reappear in its editor); pass `{ linkedEntityType,
 * linkedEntityId }` for the docs an entity is a context REFERENCE of (provenance).
 */
export const listContextDocuments = (
  storylineId: string,
  scope?: {
    entityType?: string;
    entityId?: string;
    linkedEntityType?: string;
    linkedEntityId?: string;
  },
) => {
  const params = new URLSearchParams();
  if (scope?.entityType && scope?.entityId) {
    params.set("entityType", scope.entityType);
    params.set("entityId", scope.entityId);
  }
  if (scope?.linkedEntityType && scope?.linkedEntityId) {
    params.set("linkedEntityType", scope.linkedEntityType);
    params.set("linkedEntityId", scope.linkedEntityId);
  }
  const q = params.toString() ? `?${params.toString()}` : "";
  return request<ContextDocument[]>(`/storylines/${storylineId}/context-docs${q}`);
};
/**
 * A world's context docs **without their text** — the rows the story player's `@` menu
 * lists. Same order as `listContextDocuments`, minus every document body.
 */
export const listContextDocumentIndex = (storylineId: string) =>
  request<ContextDocumentIndexEntry[]>(`/storylines/${storylineId}/context-docs/index`);
export const createContextDocument = (storylineId: string, doc: ContextDocumentInput) =>
  post<ContextDocument>(`/storylines/${storylineId}/context-docs`, doc);
export const bulkCreateContextDocuments = (
  storylineId: string,
  docs: ContextDocumentInput[],
) => post<ContextDocument[]>(`/storylines/${storylineId}/context-docs/bulk`, { docs });
export const updateContextDocument = (
  docId: string,
  body: Partial<ContextDocumentInput>,
) => patch<ContextDocument>(`/context-docs/${docId}`, body);
export const deleteContextDocument = (docId: string) => del(`/context-docs/${docId}`);

/** Link a document to an entity as a context reference (build lineage / manual). Idempotent. */
export const addDocumentLink = (
  docId: string,
  link: { entityType: EntityScope; entityId: string },
) => post<ContextDocument>(`/context-docs/${docId}/links`, link);
/** Remove a doc→entity provenance link (leaves the document). Returns the updated doc. */
export const removeDocumentLink = (
  docId: string,
  link: { entityType: EntityScope; entityId: string },
) =>
  request<ContextDocument>(
    `/context-docs/${docId}/links?entityType=${encodeURIComponent(link.entityType)}&entityId=${encodeURIComponent(link.entityId)}`,
    { method: "DELETE" },
  );

// ---- RAG corpus status + re-embed (the vector store) ----
export type RagStatus = { available: boolean; indexed: number };
export type RagEvent =
  | { stage: "embedding"; index: number; total: number; name: string; type: string }
  | { stage: "done"; indexed: number; skipped: number; total: number; available: boolean }
  | { stage: "error"; message: string };

/** Is the vector store reachable, and how many entries does this world have indexed? */
export const getRagStatus = (storylineId: string) =>
  request<RagStatus>(`/storylines/${storylineId}/rag/status`);

/** Re-embed a world's whole corpus, streaming one event per entry then a summary. */
export const reindexCorpusStream = (storylineId: string, signal?: AbortSignal) =>
  postNdjson<RagEvent>(`/storylines/${storylineId}/rag/reindex/stream`, {}, signal);

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

/** A character's currently persisted stat values (only keys ever explicitly set). */
export const getCharacterStats = (id: string) =>
  request<Record<string, number>>(`/characters/${id}/stats`);

// ---- stat definitions (universal stats on a storyline) ----
// Each definition is shared by every character; bands ("tickers") describe what
// value ranges mean. The range/bands are freely editable; delete prunes values.

/** Create payload — sensible server defaults fill visibility/appliesTo/guidance. */
export type StatDefinitionInput = Pick<
  StatDefinition,
  "key" | "displayName" | "min" | "max" | "default"
> &
  Partial<Pick<StatDefinition, "description" | "bands" | "visibility" | "appliesTo" | "guidance">>;

/** PATCH payload — key is immutable; everything else (incl. range/bands) editable. */
export type StatDefinitionUpdate = Partial<Omit<StatDefinition, "key">>;

export const listStatDefinitions = (storylineId: string) =>
  request<StatDefinition[]>(`/storylines/${storylineId}/stats`);
export const createStatDefinition = (storylineId: string, body: StatDefinitionInput) =>
  post<StatDefinition>(`/storylines/${storylineId}/stats`, body);
export const updateStatDefinition = (
  storylineId: string,
  key: string,
  body: StatDefinitionUpdate,
) => patch<StatDefinition>(`/storylines/${storylineId}/stats/${key}`, body);
export const deleteStatDefinition = (storylineId: string, key: string) =>
  del(`/storylines/${storylineId}/stats/${key}`);

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
  artStyle?: ArtStyleId;
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
  artStyle?: ArtStyleId;
}) => post<PortraitResult>("/characters/portrait", body);

export const proposeStartingStats = (body: {
  storylineId: string;
  name?: string;
  role?: string | null;
  traits?: string | null;
  personality?: string | null;
  background?: string | null;
}) => post<StartingStatsResult>("/characters/starting-stats", body);

/** Proposed voice & tone samples (situation → sample-response pairs). */
export interface VoiceSamplesResult {
  samples: VoiceSample[];
}

/** Derive a voice/tone profile from a character's prose (before starting stats). */
export const proposeVoiceSamples = (body: {
  name?: string;
  role?: string | null;
  traits?: string | null;
  speech?: string | null;
  background?: string | null;
  personality?: string | null;
  storylineId?: string | null;
}) => post<VoiceSamplesResult>("/characters/voice-samples", body);

// ---- settings ----
export const createSetting = (storylineId: string, body: SettingInput) =>
  post<Setting>(`/storylines/${storylineId}/settings`, body);
export const updateSetting = (id: string, body: Partial<SettingInput>) =>
  patch<Setting>(`/settings/${id}`, body);
export const deleteSetting = (id: string) => del(`/settings/${id}`);

// ---- setting authoring (the agentic Setting Creator) ----
// Produces a setting's base description + current state only (§4.1 node
// properties) — never the event timeline (play-accrued) or graph edges.
// `docsOverview` is inline dropped-file text used to ground one generation (no RAG).

/** A setting drafted from a seed (fills the create form). */
export interface SettingDraftResult {
  name: string;
  type: string;
  desc: string;
  atmosphere: string;
  features: string;
  currentState: string;
}

export interface SceneArtPromptResult {
  positive: string;
  negative: string;
}

export interface SceneArtResult {
  /** Relative `/media/scenes/...` URL of the saved WebP establishing image. */
  image: string;
}

export const draftSetting = (seed: string, docsOverview?: string, storylineId?: string) =>
  post<SettingDraftResult>("/settings/draft", { seed, docsOverview, storylineId });

export const generateSceneArtPrompts = (body: {
  name?: string;
  type?: string | null;
  desc?: string | null;
  atmosphere?: string | null;
  features?: string | null;
  currentState?: string | null;
  notes?: string | null;
  artStyle?: ArtStyleId;
}) => post<SceneArtPromptResult>("/settings/scene-art-prompts", body);

export const generateSceneArt = (body: {
  positive: string;
  negative?: string;
  baseUrl?: string;
  workflow?: string;
  width?: number;
  height?: number;
  steps?: number;
  cfg?: number;
  artStyle?: ArtStyleId;
}) => post<SceneArtResult>("/settings/scene-art", body);

// ---- scenarios ----
export const createScenario = (storylineId: string, body: ScenarioInput) =>
  post<Scenario>(`/storylines/${storylineId}/scenarios`, body);
export const updateScenario = (id: string, body: Partial<ScenarioInput>) =>
  patch<Scenario>(`/scenarios/${id}`, body);
export const deleteScenario = (id: string) => del(`/scenarios/${id}`);

// ---- scenario authoring (the agentic Scenario Creator) ----
// Drafts a scenario from a seed, picking a valid cast + setting from the active
// world's real roster (the backend resolves names→ids and drops dangling refs).

/** A scenario drafted from a seed (fills the create form). */
export interface ScenarioDraftResult {
  title: string;
  genre: string;
  tone: string;
  goal: string;
  opening: string;
  /** Character ids resolved from the world roster (never invented). */
  castIds: string[];
  /** Setting id resolved from the world roster, or "" when none matched. */
  settingId: string;
}

export const draftScenario = (seed: string, storylineId?: string, docsOverview?: string) =>
  post<ScenarioDraftResult>("/scenarios/draft", { seed, docsOverview, storylineId });

export const generateScenarioSceneArtPrompts = (body: {
  title?: string;
  genre?: string | null;
  tone?: string | null;
  goal?: string | null;
  opening?: string | null;
  settingName?: string | null;
  settingDesc?: string | null;
  notes?: string | null;
  artStyle?: ArtStyleId;
}) => post<SceneArtPromptResult>("/scenarios/scene-art-prompts", body);

export const generateScenarioSceneArt = (body: {
  positive: string;
  negative?: string;
  baseUrl?: string;
  workflow?: string;
  width?: number;
  height?: number;
  steps?: number;
  cfg?: number;
  artStyle?: ArtStyleId;
}) => post<SceneArtResult>("/scenarios/scene-art", body);

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

/**
 * How much of a turn's thinking the player sees.
 * - `hidden`  — none; the muted thought line is suppressed too.
 * - `summary` — the character's own in-voice `internal_thought` (default).
 * - `full`    — additionally streams the model's raw deliberation live.
 */
export type ReasoningVisibility = "hidden" | "summary" | "full";

/** One entry in the provider dropdown. Pure config — the backend needs no I/O to build it. */
export interface LlmProviderOption {
  id: string;
  label: string;
  /** Already has a base URL or a key stored. Never reveals either. */
  configured: boolean;
  /** Prefilled when switching to this provider with nothing set. */
  defaultBaseUrl: string;
  /**
   * False where the provider cannot list its models over the wire, so the UI
   * shows a text field rather than an empty dropdown that looks broken.
   */
  supportsDiscovery: boolean;
  /**
   * False where the turn loop cannot yet parse this provider's stream. Selecting
   * it works, but every turn arrives as one block instead of typing out — so the
   * picker says so rather than letting an operator find out mid-scene.
   */
  streamingDispatched: boolean;
}

export interface LlmConfig {
  baseUrl: string;
  model: string;
  provider: string;
  params: LlmParams;
  hasApiKey: boolean;
  apiKeyHint: string | null;
  /**
   * How many characters/settings the world build drafts concurrently (and how many
   * entities a RAG re-index embeds concurrently). Bounded by what the backend serves:
   * single-slot llama.cpp → 1, vLLM → higher. Images always render sequentially.
   */
  authoringConcurrency: number;
  /**
   * Fallback context-window size (tokens) used when the engine doesn't report one.
   * The live value is always available via `getLlmContextWindow()`.
   */
  maxContextTokens: number;
  /** How much of a turn's thinking reaches the player. */
  reasoningVisibility: ReasoningVisibility;
  /**
   * Every provider this build knows about. Sent with the config so the picker
   * needs no second request — and so the frontend never hardcodes the list,
   * which is the thing that goes stale between releases.
   */
  providers: LlmProviderOption[];
}

/** PATCH payload. Omit `apiKey` to keep the stored key; "" clears it. */
export interface LlmConfigUpdate {
  baseUrl?: string;
  model?: string;
  provider?: string;
  params?: LlmParams;
  apiKey?: string;
  authoringConcurrency?: number;
  maxContextTokens?: number;
  reasoningVisibility?: ReasoningVisibility;
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

/**
 * One selectable art style. `label`/`blurb` name the look for the picker; the three `lora*`
 * fields are the **effective** values — the catalog's defaults with the operator's Options
 * override folded in. `loraName` is empty when the style renders with the workflow's LoRA
 * node bypassed.
 */
export type { ArtStyleId };

export interface ArtStyleRead {
  id: ArtStyleId;
  label: string;
  blurb: string;
  loraName: string;
  loraStrength: number;
  loraEnabled: boolean;
}

/** The writable slice of a style: which LoRA it uses, how strongly, and whether at all. */
export interface ArtStyleOverride {
  loraName?: string;
  loraStrength?: number;
  loraEnabled?: boolean;
}

export interface ComfyConfig {
  baseUrl: string;
  workflow: string;
  params: ComfyParams;
  /** The default look for every generated image; each surface's picker overrides it. */
  artStyle: ArtStyleId;
  /** The full style catalog with effective LoRA settings, in display order. */
  styles: ArtStyleRead[];
}

export type ComfyConfigUpdate = Partial<Omit<ComfyConfig, "styles">> & {
  /** Patch of per-style LoRA overrides, keyed by style id. Merged, not replaced. */
  styles?: Partial<Record<ArtStyleId, ArtStyleOverride>>;
};

export interface ComfyStatusResult {
  ok: boolean;
  comfyuiVersion: string;
  device: string;
  pythonVersion: string;
}

export interface ComfyWorkflowsResult {
  workflows: string[];
}

/** One editable writing prompt's catalog entry (metadata + default text). */
export interface PromptSpec {
  key: string;
  /** Agent group label ("Character" | "Narrator" | "Director" | "Planner"). */
  agent: string;
  label: string;
  description: string;
  default: string;
}

/**
 * The writing-agent prompts payload: the full catalog + the stored global overrides.
 * A prompt key absent from `overrides` uses its catalog `default`.
 */
export interface PromptsConfig {
  catalog: PromptSpec[];
  overrides: Record<string, string>;
}

/** PATCH payload: a blank value clears a key (reverts it to the registry default). */
export interface PromptsConfigUpdate {
  overrides: Record<string, string>;
}

export interface AppSettings {
  llm: LlmConfig;
  library: LibraryDefaults;
  comfy: ComfyConfig;
  prompts: PromptsConfig;
}

export interface LlmModelsResult {
  models: string[];
  /**
   * False when the endpoint could not be reached. The route still returns 200:
   * an unreachable local server is a NORMAL state, not an exception, and a 500
   * would make the Options page look broken instead of the endpoint.
   */
  ok: boolean;
  /** Human-readable reason when `ok` is false. Never a stack trace. */
  error: string | null;
  /** "endpoint" (asked and answered), "config" (declared), or "none". */
  source: "endpoint" | "config" | "none";
}

export interface LlmTestResult {
  ok: boolean;
  model: string;
  latencyMs: number;
  sample: string;
}

/** Auto-detected local inference backend info returned by `GET /api/options/llm/backend`. */
export interface LlmBackendInfo {
  /**
   * Detected engine: "vllm" | "llamacpp" | "relay" | "unknown". "relay" is an
   * OpenAI-protocol front end naming its upstream engine; "unknown" matched no probe.
   */
  backend: string;
  /** Reasoning effort → thinking-token budget ladder. */
  budgets: Record<string, number>;
  /** The request key(s) the thinking budget is sent under. */
  budgetKeys?: string[];
  /** Whether any thinking budget is sent at all for this endpoint. */
  budgetApplied?: boolean;
}

/** Context-window size returned by `GET /api/options/llm/context-window`. */
export interface LlmContextWindow {
  /** Effective context-window size in tokens. */
  maxContextTokens: number;
  /**
   * How the value was determined: `"detected"` when the engine reported it
   * directly, `"configured"` when the stored fallback was used instead.
   */
  source: "detected" | "configured";
}

export const getSettings = () => request<AppSettings>("/options");
export const updateLlmConfig = (body: LlmConfigUpdate) =>
  patch<LlmConfig>("/options/llm", body);
export const updateLibraryDefaults = (body: LibraryDefaultsUpdate) =>
  patch<LibraryDefaults>("/options/library", body);
/**
 * Ask a provider what it serves.
 *
 * `provider` probes one WITHOUT switching to it, so an operator can find out
 * whether a new endpoint works before giving up the one that does. Omitted =
 * the active provider.
 */
export const fetchLlmModels = (body: {
  baseUrl?: string;
  apiKey?: string;
  provider?: string;
}) => post<LlmModelsResult>("/options/llm/models", body);
export const testLlmConnection = (body: {
  baseUrl?: string;
  apiKey?: string;
  provider?: string;
  model: string;
  params?: LlmParams;
}) => post<LlmTestResult>("/options/llm/test", body);
export const getLlmBackend = () => request<LlmBackendInfo>("/options/llm/backend");
export const getLlmContextWindow = () =>
  request<LlmContextWindow>("/options/llm/context-window");

/**
 * A named point in the space the scene controls already describe. `blurb` names the trade,
 * not the numbers — those are visible in the controls directly beneath it.
 */
export interface ScenePreset {
  id: string;
  label: string;
  blurb: string;
  values: { maxTurns: number; suggestionsCount: number; beatLength: BeatLength };
}

export const getScenePresets = () =>
  request<ScenePreset[]>("/options/scene-presets");

// ---- narrative style guide ----

/** One field of a style guide, as the editor renders it. */
export interface StyleBlockSpec {
  id: string;
  label: string;
  helper: string;
  placeholder: string;
  /** Which agent reads it: `prose` | `planner` | `both`. */
  reader: string;
  /** `prefix` (the cached system message) | `tail` (re-read every beat). */
  placement: string;
}

/**
 * One applicable preset. `builtin` presets cannot be renamed or deleted; applying either
 * kind COPIES its blocks into the storyline's own fields, so nothing here is a live
 * reference and every block stays editable afterwards.
 */
export interface StylePreset {
  id: string;
  name: string;
  blurb: string;
  blocks: Record<string, string>;
  builtin: boolean;
}

export interface StyleCatalog {
  blocks: StyleBlockSpec[];
  presets: StylePreset[];
}

/** The block catalog + every applicable preset. One call: both editor surfaces need both. */
export const getStyleGuide = () => request<StyleCatalog>("/options/style-guide");

export const saveStylePreset = (body: { id: string; name: string; blocks: Record<string, string> }) =>
  post<StyleCatalog>("/options/style-presets", body);

export const deleteStylePreset = (id: string) =>
  // `request` directly rather than the shared `del`, which is typed to void: this endpoint
  // answers with the refreshed catalog so the caller never needs a follow-up read.
  request<StyleCatalog>(`/options/style-presets/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
export const updatePromptsConfig = (body: PromptsConfigUpdate) =>
  patch<PromptsConfig>("/options/prompts", body);

// ---- ComfyUI image generation ----
export const updateComfyConfig = (body: ComfyConfigUpdate) =>
  patch<ComfyConfig>("/options/comfy", body);
export const fetchComfyWorkflows = () =>
  request<ComfyWorkflowsResult>("/options/comfy/workflows");
export const checkComfyStatus = (body: { baseUrl?: string }) =>
  post<ComfyStatusResult>("/options/comfy/status", body);
/** LoRA files the configured ComfyUI server offers. Empty when it is unreachable — the
 * Options field falls back to free text rather than blocking the save. */
export const fetchComfyLoras = () => request<{ loras: string[] }>("/options/comfy/loras");

// ---- Orphaned-media cleanup ----

/** Per-directory breakdown within a MediaOrphansResult. */
export interface MediaDirOrphans {
  orphanCount: number;
  eligibleCount: number;
  totalBytes: number;
  eligibleBytes: number;
}

/** Dry-run scan result from `GET /api/options/media/orphans`. */
export interface MediaOrphansResult {
  portraits: MediaDirOrphans;
  scenes: MediaDirOrphans;
  /** In-play scene images captured from the story player (`/media/moments`). */
  moments: MediaDirOrphans;
  orphanCount: number;
  eligibleCount: number;
  totalBytes: number;
  eligibleBytes: number;
  minAgeHours: number;
}

/** Cleanup result from `POST /api/options/media/cleanup`. */
export interface MediaCleanupResult {
  deletedCount: number;
  freedBytes: number;
  skippedRecentCount: number;
}

/** Scan for orphaned WebP files (dry-run, no deletions). */
export const getMediaOrphans = (minAgeHours?: number) =>
  request<MediaOrphansResult>(
    `/options/media/orphans${minAgeHours !== undefined ? `?min_age_hours=${minAgeHours}` : ""}`,
  );

/** Delete eligible orphaned WebP files (grace-period expired). */
export const cleanupMediaOrphans = (minAgeHours?: number) =>
  request<MediaCleanupResult>(
    `/options/media/cleanup${minAgeHours !== undefined ? `?min_age_hours=${minAgeHours}` : ""}`,
    { method: "POST" },
  );

// ---- Story Graph (Neo4j substrate) ----
// The scenario subgraph read live on load, plus the Type Registry (§1.4). These
// degrade gracefully: `getScenarioGraph` returns `{ available: false, … }` when
// the graph is off. Built-in registry types are immutable (the backend 409s).

/** Input for registering a user-defined graph type (edges require a valence). */
export type GraphTypeInput = Pick<
  GraphTypeDefinition,
  "kind" | "typeName" | "fieldSchema" | "description" | "valence" | "decay"
>;

export const getScenarioGraph = (scenarioId: string) =>
  request<ScenarioGraph>(`/scenarios/${scenarioId}/graph`);
export const listGraphTypes = (storylineId: string) =>
  request<GraphTypeDefinition[]>(`/storylines/${storylineId}/graph/types`);
export const createGraphType = (storylineId: string, body: GraphTypeInput) =>
  post<GraphTypeDefinition>(`/storylines/${storylineId}/graph/types`, body);
export const updateGraphType = (
  typeId: string,
  body: Partial<GraphTypeInput> & { status?: GraphTypeDefinition["status"] },
) => patch<GraphTypeDefinition>(`/graph/types/${typeId}`, body);
export const deleteGraphType = (typeId: string) => del(`/graph/types/${typeId}`);

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
