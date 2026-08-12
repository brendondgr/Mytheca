// Turn-loop NDJSON event types — the wire shape streamed by
// `POST /api/play/{scenarioId}/turn` (docs/api-contract.md → NDJSON Event Stream).
// Mirrors the backend discriminated union in `web/backend/app/events/envelope.py`.
// Kept distinct from the authoring `EventTag`/`Branch` types in `@/lib/types`.

export type PlayVisibility =
  | "public"
  | "private_to_user"
  | "private_to_character"
  | "hidden";

interface PlayEnvelope {
  id: string;
  seq: number;
  scenarioId: string;
  sessionId: string;
  ts: string;
  visibility: PlayVisibility;
}

/** Narrator prose. Delta-streamed: same id, incremental `text`, `done` flips true last. */
export interface NarrationEvent extends PlayEnvelope {
  type: "narration";
  data: { text: string; done: boolean };
}

/** A character's spoken line. Delta-streamed (same id, incremental `text`, `done`). */
export interface CharacterDialogueEvent extends PlayEnvelope {
  type: "character_dialogue";
  data: { characterId: string; text: string; done: boolean };
}

/** A character's physical beat. Sent as one full event. */
export interface CharacterActionEvent extends PlayEnvelope {
  type: "character_action";
  data: { characterId: string; text: string };
}

/** A stat change carried on a state_update (no dice — D11). */
export interface StatPatch {
  characterId: string;
  key: string;
  delta?: number | null;
  value?: number | null;
  reason: string;
}

/** A scenario-state / stat change. Sent as one full event (drives side panels). */
export interface StateUpdateEvent extends PlayEnvelope {
  type: "state_update";
  data: { patch: Record<string, unknown>; stat?: StatPatch | null };
}

/** One branch fork — label + a narrative-direction `outcome` (no `check`, D11). */
export interface BranchChoiceOption {
  label: string;
  outcome: string;
}

export interface BranchChoicesEvent extends PlayEnvelope {
  type: "branch_choices";
  data: { choices: BranchChoiceOption[] };
}

/**
 * A character's private thought. Streamed to the player (`visibility: private_to_user`)
 * as its own "thinking" bubble, but kept out of other characters' context server-side.
 */
export interface InternalThoughtEvent extends PlayEnvelope {
  type: "internal_thought";
  data: { characterId: string; text: string };
}

/**
 * A character's runtime scene presence. `present` is the only selectable status (they can
 * be picked to speak); the others keep them in the cast but out of the speaking pool.
 */
export type PresenceStatus = "present" | "unconscious" | "departed" | "left" | "dead";

/**
 * A character's scene-presence transition (Scene Presence & Director Actions). `auto` is
 * true when the engine detected it (a stat trigger, the director's exit, or a
 * self-declaration) — the client offers an undo — and false for a manual player override.
 */
export interface CharacterStatusChangeEvent extends PlayEnvelope {
  type: "character_status_change";
  data: { characterId: string; status: PresenceStatus; reason: string; auto: boolean };
}

/** Any story event on the turn stream. */
export type PlayEvent =
  | NarrationEvent
  | CharacterDialogueEvent
  | CharacterActionEvent
  | StateUpdateEvent
  | BranchChoicesEvent
  | InternalThoughtEvent
  | CharacterStatusChangeEvent;

/** Terminal in-band error frame (mid-stream failure). */
export interface TurnErrorFrame {
  type: "error";
  message: string;
}

/**
 * Diagnostic trace frame (opt-in via `trace: true`) — the ordered, plain-language
 * record of what the turn loop did and why (Director choice, hidden thinking, stat
 * clamps, re-ranks, reflection). Rendered by the Inspector panel; ignored by the
 * transcript. `step` is a stable key (`turn` opens each turn); `n` orders within a turn.
 */
export interface TurnTraceFrame {
  type: "trace";
  n: number;
  step: string;
  title: string;
  detail: string;
  data: Record<string, unknown>;
}

/** One line of the turn stream. */
export type TurnStreamFrame = PlayEvent | TurnErrorFrame | TurnTraceFrame;

// ---- persisted session review (GET /play/{scenarioId}/sessions[/{id}]) ----

/** One saved play-through's metadata (the resume list, newest `updatedAt` first). */
export interface SessionSummary {
  id: string;
  scenarioId: string;
  createdAt: string;
  updatedAt: string;
  closedAt: string | null;
  /** Number of player turns taken. */
  turnCount: number;
  /** The first player line — a human label for the play-through. */
  preview: string;
}

/**
 * A persisted story event in the wire-envelope shape, so the story player can replay it
 * through the exact reducers it uses live (reload = replay). `type` widens to include
 * `user_turn` (the player line, persisted but never streamed live).
 */
export interface PersistedEvent {
  type: string;
  id: string;
  seq: number;
  scenarioId: string;
  sessionId: string;
  ts: string;
  visibility: PlayVisibility;
  data: Record<string, unknown>;
}

/** A persisted diagnostic trace step (graph/RAG/thinking) for one turn. */
export interface PersistedTrace {
  turn: number;
  n: number;
  step: string;
  title: string;
  detail: string;
  data: Record<string, unknown>;
}

/** The full record of one play-through — used to rehydrate the player on resume. */
export interface SessionHistory {
  session: SessionSummary;
  events: PersistedEvent[];
  traces: PersistedTrace[];
}

/** The body for `POST /play/{scenarioId}/turn`. */
export interface TurnRequestBody {
  text: string;
  directedAt?: string | null;
  sessionId?: string | null;
  /** Request interleaved diagnostic `trace` frames (the Inspector panel). */
  trace?: boolean;
  /**
   * The narrative-direction tag of a selected branch/path (legacy). When set, the turn
   * opened with a fuller "progression" narration and played the choice out over several beats.
   */
  outcome?: string | null;
  /**
   * Player POV: the id of the *present* cast member the player is speaking AS. When set, the
   * line IS that character's line — persisted on the `user_turn` row (`data.pov`) and locked
   * out of the AI roster server-side. `null`/omitted = the default guide/narrator behavior.
   */
  povCharacterId?: string | null;
  /**
   * The narrator direction for this turn — what should happen next and how the cast should
   * react — from the composer's second box, which appears above the message box whenever
   * `povCharacterId` is set (under POV the `text` field is the character's own line and can
   * no longer double as direction). The backend breaks it into requirements and schedules
   * them across the scene's `maxTurns` budget, so everything asked for lands in the turn.
   * Omitted with POV off means the player's `text` is itself the direction.
   */
  guidance?: string | null;
}
