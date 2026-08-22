import type { StartingStatProposal } from "@/lib/api";
import type { Branch, SettingTimelineEntry, StatDefinition, VoiceSample } from "@/lib/types";
import type { ReadDoc } from "@/lib/readDocs";

// Editor model shared by the create/edit modal. A single loose Draft covers all
// three entity types; each form reads/writes the fields it cares about. Keys
// prefixed with `_` are editor-internal (agentic prompt + "drafted by Mytheca").

export type EntityType = "character" | "setting" | "scenario";
export type EditorMode = "manual" | "agentic";

import type { AuthoredVerb } from "@/lib/sceneVerbs";

export interface Draft {
  name?: string;
  role?: string;
  color?: string;
  traits?: string;
  speech?: string;
  goal?: string;
  secret?: string;
  // Character base-identity prose + generated portrait (agentic Character Creator).
  // Nullable to mirror the Character wire shape (the form binds with `?? ""`).
  appearance?: string | null;
  background?: string | null;
  personality?: string | null;
  portrait?: string | null;
  type?: string;
  desc?: string;
  // Setting node metadata + generated establishing image (agentic Setting Creator).
  // Nullable to mirror the Setting wire shape (the form binds with `?? ""`).
  atmosphere?: string | null;
  features?: string | null;
  currentState?: string | null;
  image?: string | null;
  // Read-only on the editor: the play-accrued event timeline (shown as the §4.1 seam).
  timeline?: SettingTimelineEntry[];
  title?: string;
  genre?: string;
  tagline?: string;
  premise?: string;
  worldPrimer?: string;
  symbol?: string;
  symbolColor?: string;
  // Universal storyline stats being edited, plus a snapshot of what was loaded so
  // submit can diff into create/update/delete calls. Only on the storyline modal.
  _stats?: StatDefinition[];
  _statsOriginal?: StatDefinition[];
  tone?: string;
  cast?: string[];
  settingId?: string;
  /** The scene's own one-tap direction verbs (see `lib/sceneVerbs`). */
  directionVerbs?: AuthoredVerb[];
  // Narrator-voice scene-opening prose (drafted by the agentic Scenario Creator).
  opening?: string;
  branches?: Branch[];
  _prompt?: string;
  // Reference files dropped in the create modal, read into memory to ground a
  // single generation only (never persisted/indexed — RAG is a later plan).
  _docFiles?: ReadDoc[];
  _ai?: boolean;
  // Editor-internal portrait prompts (editable before rendering the image) and
  // the proposed starting stats (review → applied when the character is saved).
  _portraitPositive?: string;
  _portraitNegative?: string;
  _startingStats?: StartingStatProposal[];
  // Editor working copy of the character's voice & tone samples (situation →
  // sample-response pairs). Persisted with the character (`voiceSamples`), edited
  // above the Starting Stats section, and (re)generated via proposeVoiceSamples.
  _voiceSamples?: VoiceSample[];
  // Editor-internal scene-art prompts for the Setting Creator (editable before
  // rendering the establishing image).
  _sceneArtPositive?: string;
  _sceneArtNegative?: string;
  // Per-scenario writing-prompt overrides ({registry key → text}) staged in the
  // scenario editor and persisted with the scenario (`promptOverrides`).
  _promptOverrides?: Record<string, string>;
}

export interface ModalState {
  // EntityType covers the modal editors (character/setting/scenario). "begin" is the
  // begin-scene preview. ("storyline" is retained in the union only so the legacy
  // guards stay well-typed — storyline create/edit now live on their own page,
  // `StorylineCreatorView`, not a modal.)
  type: EntityType | "begin" | "storyline";
  mode: EditorMode;
  editId: string | null;
}

/** Slugify a stat display name into a stable lowercase key (e.g. "Hit Points" → "hit_points"). */
export function statKeyOf(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

/** A blank universal stat for the Statistics editor (sensible 0–100 default). */
export function blankStat(): StatDefinition {
  return {
    key: "",
    displayName: "",
    description: "",
    min: 0,
    max: 100,
    default: 50,
    visibility: "public",
    guidance: null,
    appliesTo: ["character"],
    bands: [],
  };
}

export const DEFAULT_DRAFTS: Record<EntityType, Draft> = {
  character: { name: "", role: "", color: "#8E2B1C", traits: "", speech: "", goal: "", secret: "", appearance: "", background: "", personality: "", _portraitPositive: "", _portraitNegative: "", _voiceSamples: [] },
  setting: { name: "", type: "Social Hub", desc: "", atmosphere: "", features: "", currentState: "", _sceneArtPositive: "", _sceneArtNegative: "" },
  scenario: { title: "", genre: "Intrigue", tone: "Tension · rising", goal: "", cast: [], settingId: "", branches: [], image: null, _sceneArtPositive: "", _sceneArtNegative: "" },
};

export const EDITOR_META: Record<
  EntityType,
  { kicker: string; create: string; edit: string; ok: string; save: string; width: string }
> = {
  character: { kicker: "Character", create: "Forge a Character", edit: "Edit Character", ok: "Add to Cast", save: "Save Changes", width: "560px" },
  setting: { kicker: "Setting", create: "Add a Setting", edit: "Edit Setting", ok: "Add Setting", save: "Save Changes", width: "520px" },
  scenario: { kicker: "Scenario", create: "Assemble a Scenario", edit: "Edit Scenario", ok: "Create & Feature", save: "Save Changes", width: "600px" },
};

export const PROMPT_PLACEHOLDERS: Record<EntityType, string> = {
  character: "e.g. A weary harbor smuggler who owes the Drowned Court and wants out — secretly an informant for the Tidewatch.",
  setting: "e.g. A flooded undercroft beneath the chapel where the tide leaves strange offerings on the altar.",
  scenario: "e.g. A tense midnight negotiation over the salt ledger that turns when the Tidewatch raids the room.",
};

export const PROMPT_EXAMPLES: Record<EntityType, { short: string; full: string }[]> = {
  character: [
    { short: "A double-crossing smuggler", full: "A weary harbor smuggler who owes the Drowned Court and secretly informs for the Tidewatch." },
    { short: "A zealous inquisitor", full: "A cold inquisitor hunting salt-heresy, whose faith broke long ago." },
  ],
  setting: [
    { short: "A drowned chapel", full: "A flooded undercroft beneath the chapel where the tide leaves offerings." },
    { short: "A lantern-lit quay", full: "A boardwalk of swaying lanterns where deals outnumber the fish." },
  ],
  scenario: [
    { short: "A negotiation gone wrong", full: "A midnight negotiation over the salt ledger that turns when the Tidewatch raids." },
    { short: "A lighthouse mystery", full: "Discover who relights the dead lighthouse each midnight, and what they signal." },
  ],
};

export function isDraftValid(type: EntityType, draft: Draft): boolean {
  if (type === "character" || type === "setting") return Boolean(draft.name?.trim());
  // scenario
  return Boolean(draft.title?.trim()) && Boolean(draft.cast?.length) && Boolean(draft.settingId);
}

/** Pick a random pool item whose name/title isn't already taken (fallback: any). */
export function pickUnused<T>(pool: T[], taken: string[], keyOf: (item: T) => string): T {
  const available = pool.filter((item) => !taken.includes(keyOf(item)));
  const source = available.length ? available : pool;
  return { ...source[Math.floor(Math.random() * source.length)] };
}
