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

/** Hidden conditioning thought — withheld from the stream server-side; typed for completeness. */
export interface InternalThoughtEvent extends PlayEnvelope {
  type: "internal_thought";
  data: { characterId: string; text: string };
}

/** Any story event on the turn stream. */
export type PlayEvent =
  | NarrationEvent
  | CharacterDialogueEvent
  | CharacterActionEvent
  | StateUpdateEvent
  | BranchChoicesEvent
  | InternalThoughtEvent;

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

/** The body for `POST /play/{scenarioId}/turn`. */
export interface TurnRequestBody {
  text: string;
  directedAt?: string | null;
  sessionId?: string | null;
  /** Request interleaved diagnostic `trace` frames (the Inspector panel). */
  trace?: boolean;
}
