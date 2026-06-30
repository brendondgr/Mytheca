// Velora's core domain objects (see docs/documentation.md):
// Storyline → Characters + Settings → Scenarios (with branches). For this
// frontend pass the data is in-memory seed data; the shapes mirror the
// eventual backend contracts.

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
  /** Relative `/media/...` URL of an optional scene-art image; plate fallback. */
  image?: string | null;
  /** Persisted positive ComfyUI prompt for the scene-art image. */
  sceneArtPositive?: string | null;
  /** Persisted negative ComfyUI prompt for the scene-art image. */
  sceneArtNegative?: string | null;
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
  guidance: string | null;
  appliesTo: string[];
  bands: StatBand[];
}

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

/** A persisted, triaged reference document (the RAG corpus). */
export interface ContextDocument {
  id: string;
  storylineId: string;
  name: string;
  content: string;
  category: DocCategory;
  /** Grounds Velora's drafting (world-setting docs). */
  includeDraft: boolean;
  /** Member of the retrieval corpus (embedded into Qdrant on save). */
  includeRag: boolean;
  source: string;
  charCount: number;
  /** When set, the doc belongs to a specific character/setting/scenario editor and
   *  reappears there; when null it is a storyline-level corpus doc. */
  entityType?: EntityScope | null;
  entityId?: string | null;
}

/** One Triage classification for a dropped doc (before persistence). */
export interface TriageItem {
  name: string;
  category: DocCategory;
  includeDraft: boolean;
  includeRag: boolean;
  rationale: string;
}

/** The storyline core of a build proposal. */
export interface ProposedStoryline {
  title: string;
  genre: string;
  tagline: string;
  premise: string;
  worldPrimer: string;
}

/** A proposed starting value for one universal stat (defaults to the schema). */
export interface ProposedStartingStat {
  key: string;
  value: number;
}

/** A character drafted by the world build, plus its starting stats. */
export interface ProposedCharacter {
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
  startingStats: ProposedStartingStat[];
  /** Client-side only: the portrait URL once it renders during commit (live preview). */
  portrait?: string | null;
}

/** A setting drafted by the world build. */
export interface ProposedSetting {
  name: string;
  type: string;
  desc: string;
  atmosphere: string;
  features: string;
  currentState: string;
  /** Client-side only: the scene-art URL once it renders during commit (live preview). */
  image?: string | null;
}

/**
 * The reviewable world proposal returned by `POST /storylines/build` — drafted but
 * not persisted; the page reviews then commits it via the normal CRUD endpoints.
 */
export interface ProposedWorld {
  storyline: ProposedStoryline;
  stats: StatDefinition[];
  characters: ProposedCharacter[];
  settings: ProposedSetting[];
}

// ---- Live build / triage stream events (NDJSON) -----------------------------
// Mirror the backend event unions (app/schemas/build.py, context_document.py).
// `POST /storylines/build/stream` and `/triage/stream` emit one of these per line
// so the New Storyline page can render the world / triage as they are built.

/** One progress event from the streaming world build. */
export type BuildEvent =
  | { type: "status"; stage: string; message: string }
  | { type: "meta"; title: string; genre: string; tagline: string; premise: string }
  | { type: "primer"; worldPrimer: string }
  | { type: "plan"; stats: StatDefinition[]; characters: string[]; settings: string[] }
  | { type: "character"; index: number; total: number; character: ProposedCharacter }
  | { type: "setting"; index: number; total: number; setting: ProposedSetting }
  | { type: "done"; world: ProposedWorld }
  | { type: "error"; message: string };

/** One progress event from the streaming (per-file) triage. */
export type TriageEvent =
  | { type: "status"; name: string; index: number; total: number }
  | { type: "item"; item: TriageItem }
  | { type: "done" }
  | { type: "error"; message: string };

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
