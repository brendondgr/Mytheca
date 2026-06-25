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
