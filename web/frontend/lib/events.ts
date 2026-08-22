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

/**
 * One version of a beat's prose. A re-roll keeps the old take rather than replacing it — the
 * player asked for a *different* line, not for the previous one to stop existing.
 *
 * Takes live inside the beat's own event `data`, never as extra events: a second row would
 * need a `seq`, which would either break the `(sessionId, seq)` uniqueness or poison the
 * transcript's ordering. One beat keeps one position however many times it is re-rolled.
 */
export interface BeatTake {
  id: string;
  text: string;
  ts: string;
}

/** One rendered version of a scene image, kept for the same reason as `BeatTake`. */
export interface ImageTake {
  id: string;
  url: string;
  prompt: string;
  negative: string;
  caption: string;
  ts: string;
}

/**
 * Alternate versions of a prose beat, and which is showing. Both default to empty/zero, so
 * events written before takes existed parse unchanged. `text` always mirrors the active
 * take — it stays the single source of truth for everything that does not know takes exist.
 */
export interface Takes {
  takes?: BeatTake[];
  activeTake?: number;
}

/** Narrator prose. Delta-streamed: same id, incremental `text`, `done` flips true last. */
export interface NarrationEvent extends PlayEnvelope {
  type: "narration";
  data: { text: string; done: boolean } & Takes;
}

/**
 * A character's whole beat as one first-person passage — what they notice, do and say,
 * woven together, with spoken words in double quotes inline. Delta-streamed (same id,
 * incremental `text`, `done`). This is the form a character beat takes now;
 * `character_dialogue` / `character_action` / `internal_thought` remain for sessions
 * recorded in the older three-fragment shape.
 */
export interface CharacterProseEvent extends PlayEnvelope {
  type: "character_prose";
  data: { characterId: string; text: string; done: boolean } & Takes;
}

/** A character's spoken line. Delta-streamed (same id, incremental `text`, `done`). */
export interface CharacterDialogueEvent extends PlayEnvelope {
  type: "character_dialogue";
  data: { characterId: string; text: string; done: boolean } & Takes;
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
  data: {
    /**
     * A question from the planner, when it stopped the turn rather than guess where the
     * story goes. Empty for the ordinary end-of-turn follow-ups, which are offered rather
     * than asked. When set, the choices are suggested answers — the player may ignore them
     * and type their own.
     */
    prompt?: string;
    choices: BranchChoiceOption[];
  };
}

/**
 * A character's private thought. Streamed to the player (`visibility: private_to_user`)
 * as its own "thinking" bubble, but kept out of other characters' context server-side.
 */
export interface InternalThoughtEvent extends PlayEnvelope {
  type: "internal_thought";
  /** Delta-streamed like visible prose: accumulate by `id` until `done`. */
  data: { characterId: string; text: string; done: boolean };
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

/**
 * The scene is **asking** for a character who is not in it. Never an arrival.
 *
 * The AI has no way to bring a character in — there is no planner action for it — so this
 * changes nothing on its own. Presence moves only when the player accepts, through the same
 * manual `setPresence` path the cast rail uses. `reason` is the requirement or phrase that
 * named them, shown verbatim so the ask quotes the player's own words.
 */
export interface CastRequestEvent extends PlayEnvelope {
  type: "cast_request";
  data: { characterId: string; reason: string };
}

/**
 * A rendered picture of the moment (the player's **Create image** action). Persisted like
 * any other beat, so it takes its place in the transcript live *and* on reload. `url` is a
 * relative `/media/moments/…` path (resolve with `mediaUrl`); `caption` is the image's alt
 * text and its enlarged-view label; `prompt`/`negative` are what ComfyUI was given.
 */
export interface SceneImageEvent extends PlayEnvelope {
  type: "scene_image";
  data: {
    url: string;
    prompt: string;
    negative: string;
    caption: string;
    characterIds: string[];
    /** Alternate renders; `url`/`prompt`/`caption` above mirror the active one. */
    takes?: ImageTake[];
    activeTake?: number;
  };
}

/** Any story event on the turn stream. */
export type PlayEvent =
  | NarrationEvent
  | CharacterProseEvent
  | CharacterDialogueEvent
  | CharacterActionEvent
  | StateUpdateEvent
  | BranchChoicesEvent
  | InternalThoughtEvent
  | CharacterStatusChangeEvent
  | CastRequestEvent
  | SceneImageEvent;

/**
 * A re-roll is starting for an existing beat: **clear that message's text** before the deltas
 * that follow.
 *
 * A transport frame, not a persisted story event — nothing about it belongs in the record.
 * The deltas after it are ordinary story-event frames re-emitting the same `id` and `seq`, so
 * the accumulator needs no special case; this frame exists only because those deltas would
 * otherwise append to the take being replaced.
 */
export interface BeatRerollFrame {
  type: "beat_reroll";
  eventId: string;
  /** The index the new take will occupy once it completes. */
  take: number;
}

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
/**
 * The model's in-flight deliberation, streamed live and never persisted.
 *
 * Ephemeral by design: it is the machine's scratchpad, not story record — no `seq`, no
 * DB row, absent from resume and export. Only sent when the operator sets Reasoning
 * visibility to `full`, because raw deliberation frequently states what a character is
 * about to say before they say it.
 */
export interface TurnReasoningFrame {
  type: "reasoning";
  characterId: string | null;
  text: string;
  done: boolean;
}

export type TurnStreamFrame =
  | PlayEvent
  | TurnErrorFrame
  | TurnTraceFrame
  | TurnReasoningFrame
  | BeatRerollFrame;

// ---- scene images (POST /play/{scenarioId}/moment/stream) ----

/**
 * Progress on the moment stream: `prompt` while the agent describes the scene, `render`
 * while ComfyUI paints it (re-sent as the keep-alive heartbeat, so it may arrive more
 * than once). `positive`/`caption` are filled from the `render` stage onward.
 */
export interface MomentStageFrame {
  type: "moment_stage";
  stage: "prompt" | "render";
  message: string;
  positive: string;
  caption: string;
}

/**
 * One increment of a ghostwritten line. Incremental like every other delta here — the client
 * appends. Never persisted: the draft exists only in the composer until the player sends it.
 */
export interface GhostwriteFrame {
  type: "ghostwrite";
  text: string;
  done: boolean;
}

/** One line of the ghostwrite stream. */
export type GhostwriteStreamFrame = GhostwriteFrame | TurnErrorFrame;

/** One line of the moment stream — the two stages, the finished image, or a failure. */
export type MomentStreamFrame = MomentStageFrame | SceneImageEvent | TurnErrorFrame;

/** The body for `POST /play/{scenarioId}/moment/stream`. */
export interface MomentRequestBody {
  sessionId: string;
  /** How many recent beats the picture looks back over (clamped 2–40 server-side). */
  beats?: number;
}

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
  /** The first **non-empty** player line — the tray's fallback label. Non-empty because a
   *  text-less Continue turn writes a blank one. */
  preview: string;
  /** The player's own label for this play-through; `null` falls back to `preview`. */
  name: string | null;
  /** Set together on a forked play-through (a branch, or a rewind's pre-cut snapshot):
   *  the session it came from, and the parent `seq` the copy ran through, inclusive. */
  parentSessionId: string | null;
  forkSeq: number | null;
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
/** One thing the player is still owed, surviving from an earlier turn. */
export interface StandingItem {
  id: string;
  text: string;
  /** Who it is aimed at (`null` → the narrator's to place). */
  actorId: string | null;
  /** The player named that character themselves, so it is never silently re-owned. */
  pinned: boolean;
  /** The seq of the turn it was **first** asked for — its age, not its last failure. */
  fromTurn: number | null;
}

export interface SessionHistory {
  session: SessionSummary;
  events: PersistedEvent[];
  traces: PersistedTrace[];
  /**
   * What an earlier turn could not deliver and the next one will re-owe. Present so a
   * resumed scene can show the debt up front rather than springing it on the player
   * mid-turn.
   */
  standingDirection: StandingItem[];
}

/** The player's own line, handed back by a rewind so the scene can continue from it. */
export interface RestoredTurn {
  text: string;
  guidance: string | null;
  pov: string | null;
  taggedDocIds: string[];
}

/** What a rewind removed, and what the player gets back. */
export interface RewindResult {
  session: SessionSummary;
  cutSeq: number;
  removedEvents: number;
  removedTraces: number;
  /** The play-through holding the removed history, when a snapshot was kept. */
  snapshotSessionId: string | null;
  restoredTurn: RestoredTurn | null;
}

/** The body for `POST /play/{scenarioId}/turn`. */
export interface TurnRequestBody {
  text: string;
  /**
   * Who the line is aimed at. Set by the UI from the **first `@` cast mention in the
   * message box** — the direction box's cast mentions are the subjects of the direction,
   * not the addressee. The engine appends it to `intent.addressed` and promotes a freeform
   * line to `direct`, so the person the player named is the one who answers.
   */
  directedAt?: string | null;
  /**
   * The direction box read line-by-line, each line optionally aimed at a character the
   * player `@`-mentioned on it. Non-empty `directives` **replace** `guidance` parsing — the
   * backend uses them verbatim and spends no LLM call re-guessing what was already stated,
   * and a target the player set is never silently re-owned by the narrator. Omitted for a
   * free-prose direction, which keeps today's behaviour exactly.
   */
  directives?: { text: string; actorId: string | null }[];
  sessionId?: string | null;
  /** Request interleaved diagnostic `trace` frames (the Inspector panel). */
  trace?: boolean;
  /**
   * The narrative-direction tag of a selected branch/path. When set, the turn opens with a
   * fuller "progression" narration that plays the choice out over several beats rather than
   * answering it in one line.
   *
   * Sent by the transcript's **"Play it out"** action on a suggestion chip. (The primary
   * click still writes the suggestion into the composer to be edited — a suggestion is a
   * starting point, and the player's own wording is the point of the app.)
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
  /**
   * The storyline `ContextDocument` ids the player @-tagged in the composer. Their text is
   * loaded server-side and folded into the character + narrator prompts as **reference for
   * this one turn**, bypassing the conservative retrieval gate and its 600-character
   * snippet cap. The opposite of `guidance`: guidance is direction and becomes schedulable
   * requirements; tagged files are background and never do — the backend withholds them
   * from the intent, direction, and planner agents, so they can inform what is *said* but
   * never what *happens*. Ids from another storyline are ignored.
   */
  taggedDocIds?: string[];
  /**
   * The player pressed **Continue**: run a turn with no line from them. Valid with an empty
   * `text` — the turn must ask for *something*, and this is one of the four things that
   * counts (alongside `text`, `guidance` and `outcome`).
   */
  continuation?: boolean;
}
