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
}

export interface Setting {
  id: string;
  name: string;
  /** Setting type, e.g. "Social Hub". */
  type: string;
  desc: string;
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
  /** Multi-paragraph world description authored in the create modal. */
  premise?: string;
  /** Seal shape glyph shown left of the name (e.g. "◆"). Defaults to ◆. */
  symbol?: string;
  /** Seal color (hex) for the shape glyph. Defaults to the gold token. */
  symbolColor?: string;
  characters: Character[];
  settings: Setting[];
  scenarios: Scenario[];
}
