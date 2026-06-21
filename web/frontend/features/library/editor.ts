import type { Branch, EventTag } from "@/lib/types";

// Editor model shared by the create/edit modal. A single loose Draft covers all
// four entity types; each form reads/writes the fields it cares about. Keys
// prefixed with `_` are editor-internal (agentic prompt + "drafted by Velora").

export type EntityType = "character" | "setting" | "scenario" | "branch";
export type EditorMode = "manual" | "agentic";

export interface Draft {
  name?: string;
  role?: string;
  color?: string;
  traits?: string;
  speech?: string;
  goal?: string;
  secret?: string;
  type?: string;
  desc?: string;
  title?: string;
  genre?: string;
  tone?: string;
  cast?: string[];
  settingId?: string;
  branches?: Branch[];
  label?: string;
  check?: string;
  outcome?: string;
  tag?: EventTag;
  _prompt?: string;
  _ai?: boolean;
}

export interface ModalState {
  type: EntityType | "begin";
  mode: EditorMode;
  editId: string | null;
  /** Owning scenario id when editing/creating a branch. */
  scnId?: string;
}

export const DEFAULT_DRAFTS: Record<EntityType, Draft> = {
  character: { name: "", role: "", color: "#8E2B1C", traits: "", speech: "", goal: "", secret: "" },
  setting: { name: "", type: "Social Hub", desc: "" },
  scenario: { title: "", genre: "Intrigue", tone: "Tension · rising", goal: "", cast: [], settingId: "", branches: [] },
  branch: { label: "", check: "", outcome: "", tag: "check_request" },
};

export const EDITOR_META: Record<
  EntityType,
  { kicker: string; create: string; edit: string; ok: string; save: string; width: string }
> = {
  character: { kicker: "Character", create: "Forge a Character", edit: "Edit Character", ok: "Add to Cast", save: "Save Changes", width: "560px" },
  setting: { kicker: "Setting", create: "Add a Setting", edit: "Edit Setting", ok: "Add Setting", save: "Save Changes", width: "520px" },
  scenario: { kicker: "Scenario", create: "Assemble a Scenario", edit: "Edit Scenario", ok: "Create & Feature", save: "Save Changes", width: "600px" },
  branch: { kicker: "Storyline", create: "New Storyline Branch", edit: "Edit Branch", ok: "Add Branch", save: "Save Changes", width: "560px" },
};

export const PROMPT_PLACEHOLDERS: Record<EntityType, string> = {
  character: "e.g. A weary harbor smuggler who owes the Drowned Court and wants out — secretly an informant for the Tidewatch.",
  setting: "e.g. A flooded undercroft beneath the chapel where the tide leaves strange offerings on the altar.",
  scenario: "e.g. A tense midnight negotiation over the salt ledger that turns when the Tidewatch raids the room.",
  branch: "e.g. The player tries to bluff past the guard by claiming the Captain sent them.",
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
  branch: [
    { short: "Bluff the guard", full: "The player bluffs past the guard claiming the Captain sent them." },
    { short: "Bribe for silence", full: "The player offers coin to keep a witness quiet." },
  ],
};

export function isDraftValid(type: EntityType, draft: Draft): boolean {
  if (type === "character" || type === "setting") return Boolean(draft.name?.trim());
  if (type === "scenario")
    return Boolean(draft.title?.trim()) && Boolean(draft.cast?.length) && Boolean(draft.settingId);
  return Boolean(draft.label?.trim());
}

/** Pick a random pool item whose name/title isn't already taken (fallback: any). */
export function pickUnused<T>(pool: T[], taken: string[], keyOf: (item: T) => string): T {
  const available = pool.filter((item) => !taken.includes(keyOf(item)));
  const source = available.length ? available : pool;
  return { ...source[Math.floor(Math.random() * source.length)] };
}
