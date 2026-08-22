// Mytheca's core domain objects (see docs/documentation.md):
// Storyline → Characters + Settings → Scenarios (with branches). For this
// frontend pass the data is in-memory seed data; the shapes mirror the
// eventual backend contracts.

import type { VerbGroup } from "@/lib/sceneVerbs";

/** One situation → sample-response pair defining how a character speaks. */
/**
 * The kinds of moment a voice sample can demonstrate — the same axis the backend
 * planner reads per beat as the beat's `register`. Only the samples matching the
 * current beat (plus untagged ones) are injected into the turn prompt, so a
 * character has a concrete exemplar of themselves *not at rest*.
 */
export const VOICE_MOMENTS = ["light", "neutral", "tense", "grave"] as const;
export type VoiceMoment = (typeof VOICE_MOMENTS)[number];

export interface VoiceSample {
  /** A short description of a story event or an interaction with another character. */
  situation: string;
  /** What the character would say/do in response, in their own voice. */
  sample: string;
  /** Which kind of moment this pair shows. Empty = applies to any moment. */
  moment?: VoiceMoment | "";
}

/** The five story-event types the renderer maps 1:1 (docs/design-system.md). */
export type EventTag =
  | "check_request"
  | "branch_choices"
  | "state_update"
  | "narration"
  | "character_action";

export interface Character {
  id: string;
  name: string;
  /** Role / archetype, e.g. "Antagonist". */
  role: string;
  /** Per-character accent color (hex) for monogram ring, name, role tag. */
  color: string;
  /** 1–2 letter monogram shown in the avatar. */
  mono: string;
  /** Short trait line, e.g. "Patient · Calculating · Velvet-tongued". */
  traits: string;
  /** Voice / speech style. */
  speech: string;
  goal: string;
  secret: string;
  // Base-identity prose authored once (filled by the agentic Character Creator).
  // Nullable: the backend returns null until set.
  /** Physical appearance (species/race, age, build, features, dress). */
  appearance?: string | null;
  /** Backstory / background information. */
  background?: string | null;
  /** Fuller personality sheet (temperament, values, fears, mannerisms). */
  personality?: string | null;
  /** Relative `/media/...` URL of the generated WebP portrait; monogram fallback. */
  portrait?: string | null;
  /** Persisted positive ComfyUI prompt that produced the portrait. */
  portraitPositive?: string | null;
  /** Persisted negative ComfyUI prompt that produced the portrait. */
  portraitNegative?: string | null;
  /**
   * Voice & tone profile — situation → sample-response pairs derived from the
   * character's background/personality (before starting stats), editable in the
   * character menu and injected into the turn loop. Empty list when unauthored.
   */
  voiceSamples?: VoiceSample[];
  /**
   * How far this character's word choice may wander — a **bias on top of the beat's
   * register**, `[-2, +2]`, absent/`null` meaning neutral. It nudges the register's `top_p`
   * and nothing else; the moment still picks the row.
   */
  looseness?: number | null;
}

/**
 * One durable thing that happened at a place (§4.1 event timeline).
 * Play-accrued by the async worker; never authored at creation. Mirrors the
 * backend `SettingTimelineEntry` (docs/api-contract.md).
 */
export interface SettingTimelineEntry {
  summary: string;
  /** Where it happened, e.g. `{ scenario, turn }`. */
  origin?: Record<string, unknown> | null;
  participants: string[];
  kind: string;
  visibility: string;
}

export interface Setting {
  id: string;
  name: string;
  /** Setting type, e.g. "Social Hub". */
  type: string;
  /** Base description — the short overview/mood line shown on the card. */
  desc: string;
  // Setting Node metadata authored by the agentic Setting Creator (§4.1 node
  // properties — not graph structure). Nullable: the backend returns null until set.
  /** Sensory character — sights, sounds, smells, light, texture. */
  atmosphere?: string | null;
  /** Notable physical features / fixtures / points of interest. */
  features?: string | null;
  /** Initial here-and-now — time of day, weather, lighting, what's open/barred. */
  currentState?: string | null;
  /** Relative `/media/...` URL of an optional establishing image; plate fallback. */
  image?: string | null;
  /** Persisted positive ComfyUI prompt that produced the establishing image. */
  sceneArtPositive?: string | null;
  /** Persisted negative ComfyUI prompt that produced the establishing image. */
  sceneArtNegative?: string | null;
  /** Append-only event timeline; empty at authoring, accrues from play. */
  timeline?: SettingTimelineEntry[];
}

export interface Branch {
  label: string;
  /** Check label, e.g. "Insight · DC 15". */
  check: string;
  outcome: string;
  tag: EventTag;
}

/**
 * How much a character says in one beat, set per scene from the config popover. Mirrors the
 * backend `app.schemas.base.BeatLength` — this file is the hand-maintained half of the
 * FE↔BE contract, so the three values must stay identical to the Python `Literal`.
 */
export const BEAT_LENGTHS = ["short", "medium", "long"] as const;
export type BeatLength = (typeof BEAT_LENGTHS)[number];

/** The dropdown's rendered text. The paragraph counts are the contract, so they are shown. */
export const BEAT_LENGTH_LABELS: Record<BeatLength, string> = {
  short: "Short · 1–2 ¶",
  medium: "Medium · 2–4 ¶",
  long: "Long · 5–6 ¶",
};

export interface Scenario {
  id: string;
  title: string;
  genre: string;
  tone: string;
  goal: string;
  castIds: string[];
  settingId: string;
  /** Narrator opening line, shown in the begin-scene preview. */
  opening: string;
  branches: Branch[];
  /** Hard ceiling on character replies per player message (≥1; default 5). */
  maxTurns?: number;
  /** How many follow-up suggestions to offer at the end of a turn (0–4; 0 disables; default 4). */
  suggestionsCount?: number;
  /**
   * Depth of the recent-transcript window, **only consulted under `contextPolicy: "fixed"`**
   * (5–100). By default the window fits itself to the model's real context budget each turn,
   * because picking a beat count is a question only the app can answer.
   */
  contextBeats?: number;
  /** `"auto"` (default; absent reads as auto) fits the window to the model's context
   *  budget; `"fixed"` honours `contextBeats`. */
  contextPolicy?: "auto" | "fixed";
  /**
   * How much a CHARACTER says in one beat — short 1–2 paragraphs, medium 2–4 (default),
   * long 5–6, each paragraph at most 3–4 sentences not counting quoted dialogue. Narration
   * is unaffected; it has its own sentence spec. Mirrors the backend `BeatLength`.
   */
  beatLength?: BeatLength;
  /**
   * The named preset the play controls above were last set from, or absent/`null` for
   * *Custom*. It records **intent, not truth** — the controls stay authoritative, so moving
   * one leaves this set and the UI reads "modified" and offers a reset.
   */
  scenePreset?: string | null;
  /**
   * Whether this scene runs the ReAct planner (`"planner"`, and absent/`null` reads as
   * that) or the model-free scripted beat order (`"off"`). The scene's default; a turn may
   * still override it.
   */
  plannerMode?: "planner" | "off" | null;
  /**
   * The scene's default tie scope — how much of a speaker's relationship history reaches
   * their beat. Absent/`null` reads as `"scene"`.
   */
  tieScope?: "addressed" | "scene" | "world" | null;
  /**
   * The scene's own one-tap direction verbs, appended to the built-in bar's groups. `label`
   * is the chip, `text` is the phrasing written into the direction box for the player to
   * edit — separate on purpose, since a verb exists to hand them a sentence to argue with
   * rather than a command to fire.
   */
  directionVerbs?: { label: string; group: VerbGroup; text: string }[];
  /**
   * Per-scenario writing-prompt overrides ({registry key → prompt text}) — override the
   * storyline's prompts for this scene only. Empty/absent inherits storyline/global/default.
   */
  promptOverrides?: Record<string, string>;
  /** Relative `/media/...` URL of an optional scene-art image; plate fallback. */
  image?: string | null;
  /** Persisted positive ComfyUI prompt for the scene-art image. */
  sceneArtPositive?: string | null;
  /** Persisted negative ComfyUI prompt for the scene-art image. */
  sceneArtNegative?: string | null;
}

/**
 * Whether the configured model endpoint is actually usable right now.
 *
 * Four states, not a boolean: an endpoint that is **up while the model is absent** produces
 * exactly the same silence as one that is down, and they are different problems with
 * different fixes — a typo in Options versus a dead process.
 */
export interface LlmHealth {
  state: "reachable" | "model_missing" | "unreachable" | "unconfigured";
  backend: string;
  model: string;
  checkedAt: string;
  detail: string;
}

/** A scenario with its cast + setting resolved from id references. */
export interface ResolvedScenario extends Scenario {
  cast: Character[];
  setting: Setting;
}

/**
 * The top-level world container (see docs/documentation.md). A storyline owns
 * its own cast, places, and situations; switching the active storyline in the
 * header swaps the entire working set.
 */
export interface Storyline {
  id: string;
  title: string;
  /** Genre / world flavor, shown in the storyline switcher. */
  genre: string;
  /** One-line descriptor for the switcher menu. */
  tagline?: string;
  /** Multi-paragraph human-facing world description authored in the create modal. */
  premise?: string;
  /**
   * Agent-facing runtime context generated at creation (seed + premise + an
   * optional overview of dropped docs), then editable. Distinct from `premise`.
   */
  worldPrimer?: string;
  /** Seal shape glyph shown left of the name (e.g. "◆"). Defaults to ◆. */
  symbol?: string;
  /** Seal color (hex) for the shape glyph. Defaults to the gold token. */
  symbolColor?: string;
  /**
   * Per-storyline writing-prompt overrides ({registry key → prompt text}) — the story's
   * tone/phrasing + how the bot progresses the story. A scenario may override again.
   */
  promptOverrides?: Record<string, string>;
  characters: Character[];
  settings: Setting[];
  scenarios: Scenario[];
  // Entity counts from the API list/get endpoints — populated so the storyline
  // switcher shows accurate totals for every world, not just the active one.
  // Optional: seed data and tests that omit them still type-check.
  scenarioCount?: number;
  characterCount?: number;
  settingCount?: number;
}

/** A labeled value band ("ticker") — what a sub-range of a stat *means*. */
export interface StatBand {
  min: number;
  max: number;
  /** e.g. "Nearly dead", "Very healthy". */
  label: string;
  /**
   * Optional 1-sentence explanation of the band, written with a `{Character}`
   * placeholder that the backend substitutes with the character's name at play
   * time (e.g. "{Character} is exhausted and cannot act at full strength.").
   */
  description?: string;
}

/** Visibility — public to the player, or hidden/agent-only (mirrors the backend). */
export type StatVisibility =
  | "public"
  | "private_to_user"
  | "private_to_character"
  | "hidden";

/**
 * A universal stat defined on the storyline and shared by every character —
 * a bounded numeric value with labeled bands describing what its ranges mean.
 * Mirrors the backend `StatDefinitionRead` (docs/api-contract.md).
 */
export interface StatDefinition {
  /** Stable identifier across characters (slug); immutable after creation. */
  key: string;
  displayName: string;
  description: string;
  min: number;
  max: number;
  default: number;
  visibility: StatVisibility;
  /**
   * Does this stat survive the play-through it moved in? `false` (the default) means it is
   * scoped to that play-through and the next scene opens at the character's authored value.
   */
  carryOver?: boolean;
  guidance: string | null;
  appliesTo: string[];
  bands: StatBand[];
}

// ---- Agentic storyline editor/creator (docs/api-contract.md) ----------------
// A conversational, scope-aware agent edits a storyline's own fields (title,
// genre, tagline, premise, World Primer, stat schema) under an explicit write
// scope, plan → approve → implement. Mirrors app/schemas/storyline_edit.py.

/** Per-field agent scope — may the agent write it, and read it as context. */
export interface FieldScope {
  writable: boolean;
  readable: boolean;
}

/** The scope object shared client↔server: `{ field key → FieldScope }`. */
export type StorylineScope = Record<string, FieldScope>;

/** One turn of the client-session conversation with the storyline agent. */
export interface AgentMessage {
  role: "user" | "assistant";
  content: string;
}

/** A proposed change to one text/primer field (before → after + why). */
export interface FieldChange {
  field: string;
  before?: string;
  after?: string;
  rationale: string;
}

export type StatChangeType = "add" | "update" | "remove";

/** A proposed stat *definition* change; `schemaAltering` flags the higher-risk ones. */
export interface StatChange {
  key: string;
  changeType: StatChangeType;
  before?: StatDefinition | null;
  after?: StatDefinition | null;
  schemaAltering: boolean;
  rationale: string;
}

/** The reviewable plan for one agent turn — nothing is written until approval. */
export interface StoryPlan {
  changes: FieldChange[];
  statChanges: StatChange[];
  notes: string;
}

/** One NDJSON frame from the converse/plan stream. */
export type AgentEditFrame =
  | { type: "status"; message: string }
  | { type: "message"; delta: string; done: boolean }
  | { type: "plan"; plan: StoryPlan; baseVersion?: string | null }
  | { type: "error"; message: string };

// ---- Context documents + the triaged world build ---------------------------
// The New Storyline page drops `.txt`/`.md` files, triages them into buckets, and
// (on commit) persists them as the storyline's reference corpus. Mirrors the backend
// shapes in docs/api-contract.md.

/**
 * Triage bucket. `"select"` is a UI-only placeholder meaning "not yet categorized";
 * it is mapped to `"other"` at the API boundary and never sent to the backend.
 */
export type DocCategory = "character" | "setting" | "other" | "select";

/** Entity a context document can be scoped to (else storyline-level). */
export type EntityScope = "character" | "setting" | "scenario";

/**
 * A doc→entity provenance link — records that a document was used as context for a
 * character/setting (auto-captured at build time, plus manual links). Distinct from a
 * doc's own `entityType`/`entityId` OWNERSHIP scope: a link is a reference that leaves
 * the doc a storyline-level corpus member, and one doc may link to several entities.
 */
export interface ContextDocumentLink {
  id: string;
  entityType: EntityScope;
  entityId: string;
}

/** A persisted, triaged reference document (the RAG corpus). */
export interface ContextDocument {
  id: string;
  storylineId: string;
  name: string;
  content: string;
  category: DocCategory;
  /** Grounds Mytheca's drafting (world-setting docs). */
  includeDraft: boolean;
  /** Member of the retrieval corpus (embedded into Qdrant on save). */
  includeRag: boolean;
  /** Opt-in: mine this doc for named characters/settings during the world build. */
  includeExtract: boolean;
  source: string;
  charCount: number;
  /** When set, the doc belongs to a specific character/setting/scenario editor and
   *  reappears there; when null it is a storyline-level corpus doc. */
  entityType?: EntityScope | null;
  entityId?: string | null;
  /** Provenance links — the entities this doc was used as context for. */
  links?: ContextDocumentLink[];
}

/**
 * One context document without its text — the rows the story player's `@` menu lists.
 * The client never fetches document bodies for tagging: it sends ids on the turn and the
 * backend loads the text into the prompt itself.
 */
export interface ContextDocumentIndexEntry {
  id: string;
  name: string;
  category: DocCategory;
  charCount: number;
  entityType?: EntityScope | null;
  entityId?: string | null;
}

/** One Triage classification for a dropped doc (before persistence). */
export interface TriageItem {
  name: string;
  category: DocCategory;
  includeDraft: boolean;
  includeRag: boolean;
  /** Suggested opt-in for build-time extraction (conservative; default off). */
  includeExtract: boolean;
  rationale: string;
}

// ---- Live triage stream events (NDJSON) -------------------------------------
// Mirror the backend event union (app/schemas/context_document.py). `/triage/stream`
// emits one of these per line so the New Storyline page can render triage live.

/** One progress event from the streaming (per-file) triage. */
export type TriageEvent =
  | { type: "status"; name: string; index: number; total: number }
  | { type: "item"; item: TriageItem }
  | { type: "done" }
  | { type: "error"; message: string };

// ---- World population stream events (NDJSON) --------------------------------
// Mirror the backend frame union (app/schemas/world_populate.py).
// `/storylines/{id}/populate/stream` emits one of these per line while a freshly
// created world is filled with its generated cast + settings.

/** What the population run is doing right now. */
export type PopulateStage = "roster" | "character" | "setting";

/** Where the build's roster came from (or should come from). */
export type RosterSource = "auto" | "documents" | "invent";

/** One entity the build is going to make, and which of the author's files it came from. */
export interface RosterEntry {
  name: string;
  seed: string;
  source: string;
  docId: string | null;
  docName: string;
}

/**
 * Every frame carries `seq` — its position in the run's server-side log. The client
 * echoes the last one it saw as `fromSeq` to re-attach after a dropped connection.
 */
export type PopulateEvent =
  | {
      seq: number;
      type: "status";
      stage: PopulateStage;
      message: string;
      name: string;
      index: number;
      total: number;
    }
  /** What the run is about to build, named, before it starts. */
  | {
      seq: number;
      type: "plan";
      source: RosterSource;
      characters: RosterEntry[];
      settings: RosterEntry[];
      note: string;
    }
  /** One entity that was actually persisted — the proof it reached the world. */
  | {
      seq: number;
      type: "entity";
      stage: "character" | "setting";
      id: string;
      name: string;
      /** The character's role, or the setting's type. */
      role: string;
      image: string | null;
    }
  /** `fatal: false` = one item failed and the run continued. */
  | { seq: number; type: "error"; message: string; fatal: boolean }
  | { seq: number; type: "done"; characters: number; settings: number };

/** What the author chose in the Build-world dialog. */
export interface PopulateOptions {
  /** Generate the cast + settings at all. */
  enabled: boolean;
  /** Also render portraits / scene art (opt-in; each is a ComfyUI render). */
  withArtwork: boolean;
  /**
   * Where the roster comes from. `documents` builds exactly the people and places the
   * author's classified files name; `invent` makes them up from the premise.
   */
  source: RosterSource;
}

// ---- The Story Graph (Neo4j substrate) --------------------------------------
// One knowledge graph over the storyline's entities. Characters/Settings are
// node types; their connections are edges. The graph is read live on scenario
// load (GET /scenarios/{id}/graph) and written best-effort on Character/Setting
// authoring. Mirrors the backend shapes in docs/api-contract.md.

/** A node in the Story Graph (a Character, Setting, …). */
export interface GraphNode {
  id: string;
  /** The node's type, realized as a Neo4j label (e.g. "Character", "Setting"). */
  type: string | null;
  /** Human-readable name ("Mei", "Blackwood Tavern"). */
  label: string | null;
  storyline: string | null;
  /** Type-specific descriptive fields (the node's metadata bag). */
  metadata: Record<string, unknown>;
}

/** A directed connection between two nodes (e.g. "loves", "present_at"). */
export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  metadata: Record<string, unknown>;
}

/** The subgraph for one scenario: its cast + setting and the edges among them. */
export interface ScenarioGraph {
  /** False (with empty lists) when the graph is disabled or unreachable. */
  available: boolean;
  scenarioId: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export type GraphTypeKind = "node" | "edge";
export type GraphValence = "positive" | "negative" | "neutral";
export type GraphTypeStatus = "built_in" | "experimental" | "trusted";

/** One metadata field declared on a graph type. */
export interface GraphFieldSpec {
  name: string;
  kind: "numeric" | "enum" | "prose" | "reference" | "scalar";
  required?: boolean;
  default?: unknown;
  min?: number | null;
  max?: number | null;
  options?: string[] | null;
  edgeType?: string | null;
  description?: string;
}

/**
 * A Type Registry entry (§1.4) — the semantic definition of a node/edge type.
 * Built-in types are global + immutable; users add per-storyline types
 * (`experimental` until promoted to `trusted`). Mirrors `GraphTypeRead`.
 */
export interface GraphTypeDefinition {
  id: string;
  storylineId: string | null;
  kind: GraphTypeKind;
  typeName: string;
  fieldSchema: GraphFieldSpec[];
  description: string;
  valence: GraphValence | null;
  decay: Record<string, unknown> | null;
  status: GraphTypeStatus;
}
