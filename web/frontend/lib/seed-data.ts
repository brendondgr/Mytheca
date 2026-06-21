import type {
  Character,
  EventTag,
  ResolvedScenario,
  Scenario,
  Setting,
} from "@/lib/types";

// In-memory seed for the "Embergate" storyline — no database. Mirrors the
// authoritative reference in docs/CharacterFrontpage/. Used to populate the
// Library and the Story player; mutations live in component state and reset on
// reload.

/** Fixed parchment background behind every monogram avatar. */
export const MONOGRAM_BG = "#EDE3CD";

/** Accent palette offered when forging a character. */
export const PALETTE = [
  "#8E2B1C",
  "#A8762A",
  "#2F7D6B",
  "#3A5A78",
  "#6B4A8A",
  "#5A534A",
  "#1F8A5B",
  "#B0506A",
];

/** Setting type chips. */
export const SETTING_TYPES = [
  "Social Hub",
  "Exploration",
  "Fortress",
  "Black Market",
  "Sacred",
  "Wilderness",
];

/** Event-type chips offered when authoring a branch. */
export const EVENT_TAGS: EventTag[] = [
  "check_request",
  "branch_choices",
  "state_update",
  "narration",
  "character_action",
];

export const SEED_CHARACTERS: Character[] = [
  {
    id: "maerin",
    name: "Maerin Voss",
    role: "Antagonist",
    color: "#8E2B1C",
    mono: "MV",
    traits: "Patient · Calculating · Velvet-tongued",
    speech: "Measured and courteous; never raises her voice.",
    goal: "Keep the salt routes hidden a little longer.",
    secret: "She answers to the Drowned Court.",
  },
  {
    id: "aldous",
    name: "Brother Aldous",
    role: "Reluctant Ally",
    color: "#A8762A",
    mono: "BA",
    traits: "Guilt-ridden · Gentle · Stubborn",
    speech: "Soft, apologetic, scripture half-remembered.",
    goal: "Atone for the fire he failed to stop.",
    secret: "He set the fire.",
  },
  {
    id: "wren",
    name: "Wren Calloway",
    role: "Wildcard",
    color: "#2F7D6B",
    mono: "WC",
    traits: "Quick · Wry · Loyal-ish",
    speech: "Clipped, sardonic, thick with dock-cant.",
    goal: "Earn enough coin to leave Embergate for good.",
    secret: "She has sold you out once already.",
  },
  {
    id: "doran",
    name: "Captain Doran Hale",
    role: "Lawful Blocker",
    color: "#3A5A78",
    mono: "DH",
    traits: "Dutiful · Rigid · Honourable",
    speech: "Formal and terse — strictly by the book.",
    goal: "Restore order to a rotting harbor.",
    secret: "His own brother runs the Drowned Market.",
  },
  {
    id: "nyssa",
    name: "Nyssa, Oracle of Salt",
    role: "Guide",
    color: "#6B4A8A",
    mono: "N",
    traits: "Cryptic · Serene · Knowing",
    speech: "Slow and layered; she speaks in tides.",
    goal: "See the vision through to its bitter end.",
    secret: "She is going blind to the future, not the world.",
  },
  {
    id: "grimm",
    name: "Grimm",
    role: "Threat",
    color: "#5A534A",
    mono: "G",
    traits: "Brutal · Brief · Bought",
    speech: "Few words, and most of them threats.",
    goal: "Get paid and get gone.",
    secret: "He is terrified of deep water.",
  },
];

export const SEED_SETTINGS: Setting[] = [
  {
    id: "saltworn",
    name: "The Saltworn Tavern",
    type: "Social Hub",
    desc: "Lamplit and low-beamed — every secret here has a price.",
  },
  {
    id: "harbor",
    name: "Embergate Harbor",
    type: "Exploration",
    desc: "Fog, brine, and the groan of a hundred moored hulls.",
  },
  {
    id: "keep",
    name: "Tidewatch Keep",
    type: "Fortress",
    desc: "The guard's stone fist clenched over the bay.",
  },
  {
    id: "market",
    name: "The Drowned Market",
    type: "Black Market",
    desc: "Below the tideline, where nothing is illegal.",
  },
  {
    id: "sanctum",
    name: "The Oracle's Sanctum",
    type: "Sacred",
    desc: "Salt-circles and the hush before a truth.",
  },
];

export const SEED_SCENARIOS: Scenario[] = [
  {
    id: "embergate",
    title: "The Embergate Conspiracy",
    genre: "Intrigue",
    tone: "Tension · rising",
    goal: "Uncover who smuggles sorcerer's salt through the harbor — before the Tidewatch does.",
    castIds: ["maerin", "aldous", "wren", "doran"],
    settingId: "saltworn",
    opening:
      "Lamplight gutters across the Saltworn's long tables. Maerin Voss has not looked up from her ledger once — which is how you know she has already seen you.",
    branches: [
      {
        label: "Confront Maerin at her table",
        check: "Insight · DC 15",
        outcome: "She lets a name slip — Suspicion +2",
        tag: "check_request",
      },
      {
        label: "Bargain — silence for the ledger",
        check: "Persuasion · DC 20",
        outcome: "Gain the smuggling routes — Trust −1",
        tag: "branch_choices",
      },
      {
        label: "Expose her to Captain Hale",
        check: "Deception · DC 15",
        outcome: "Hale's favour +3 — the room turns on you",
        tag: "state_update",
      },
    ],
  },
  {
    id: "salt",
    title: "Salt & Secrets",
    genre: "Social",
    tone: "Quiet · charged",
    goal: "Earn the Oracle's trust so she will read the drowned ledger aloud.",
    castIds: ["nyssa", "aldous", "wren"],
    settingId: "sanctum",
    opening:
      "Salt-circles ring the cold stone floor. The Oracle's breathing is the only sound — slow as a tide that has all the time in the world.",
    branches: [
      {
        label: "Offer a true confession",
        check: "Insight · DC 15",
        outcome: "The Oracle softens — Trust +2",
        tag: "check_request",
      },
      {
        label: "Read the salt-circles yourself",
        check: "Arcana · DC 20",
        outcome: "A vision, half-understood",
        tag: "narration",
      },
      {
        label: "Lie about why you came",
        check: "Deception · DC 20",
        outcome: "She knows — Patience −2",
        tag: "state_update",
      },
    ],
  },
  {
    id: "heist",
    title: "The Drowned Market Heist",
    genre: "Exploration · Combat",
    tone: "Volatile",
    goal: "Lift the harbor ledger from the vault before the tide returns to flood it.",
    castIds: ["wren", "grimm", "doran"],
    settingId: "market",
    opening:
      "The Drowned Market reeks of brine and tallow. Somewhere above, the bells begin to count down the turning of the tide.",
    branches: [
      {
        label: "Slip past the tide-wardens",
        check: "Stealth · DC 15",
        outcome: "Reach the vault unseen",
        tag: "check_request",
      },
      {
        label: "Pay Grimm to look away",
        check: "Persuasion · DC 10",
        outcome: "Coin −50 — a clear path",
        tag: "branch_choices",
      },
      {
        label: "Take the ledger by force",
        check: "Athletics · DC 20",
        outcome: "Alarm raised — roll Initiative",
        tag: "character_action",
      },
    ],
  },
];

// ---- Agentic "draft with Velora" pools (faked generation, no model call) ----

export const AI_CHARACTERS: Omit<Character, "id" | "mono">[] = [
  {
    name: "Seraphine Dusk",
    role: "Femme Fatale",
    color: "#B0506A",
    traits: "Magnetic · Dangerous · Unhurried",
    speech: "Low, amused — every word a lure.",
    goal: "Collect the debts the harbor pretends not to owe.",
    secret: "She is Maerin's estranged sister.",
  },
  {
    name: "Old Tobias",
    role: "Keeper of Tales",
    color: "#7A5A2A",
    traits: "Garrulous · Kindly · Sharp",
    speech: "Rambling and warm, salted with proverbs.",
    goal: "Keep the Saltworn standing one more winter.",
    secret: "He launders coin for three rival crews.",
  },
  {
    name: "Sister Vael",
    role: "Inquisitor",
    color: "#4A4A6A",
    traits: "Cold · Precise · Relentless",
    speech: "Clipped questions, never a wasted word.",
    goal: "Root out the salt-heresy at any cost.",
    secret: "Her faith broke years ago; she serves only the hunt.",
  },
  {
    name: "Pip",
    role: "Street Urchin",
    color: "#1F8A5B",
    traits: "Fast · Fearless · Hungry",
    speech: "Breathless, slangy, all elbows.",
    goal: "Earn a place on any crew that will have her.",
    secret: "She has been following you for a week.",
  },
];

export const AI_SETTINGS: Omit<Setting, "id">[] = [
  {
    name: "The Lantern Quay",
    type: "Exploration",
    desc: "A boardwalk of swaying lights where deals outnumber the fish.",
  },
  {
    name: "Smuggler's Stair",
    type: "Black Market",
    desc: "Wet stone steps spiralling down to water that should not be there.",
  },
  {
    name: "The Glass Conservatory",
    type: "Sacred",
    desc: "A drowned greenhouse where salt blooms like frost on every pane.",
  },
  {
    name: "Gull's Rest Light",
    type: "Fortress",
    desc: "A lighthouse that hasn't burned in years — yet someone keeps the lamp lit.",
  },
];

export const AI_SCENARIOS: Pick<
  Scenario,
  "title" | "genre" | "tone" | "goal"
>[] = [
  {
    title: "The Lighthouse Pact",
    genre: "Mystery",
    tone: "Eerie · still",
    goal: "Discover who relights Gull's Rest each midnight — and what they signal.",
  },
  {
    title: "A Debt in Salt",
    genre: "Intrigue",
    tone: "Pressing",
    goal: "Settle Seraphine's ledger before she settles it in blood.",
  },
  {
    title: "The Tidewatch Mutiny",
    genre: "Drama · Combat",
    tone: "Boiling",
    goal: "Hold the Keep together as Hale's own guard turns against him.",
  },
];

export const AI_BRANCHES: Scenario["branches"] = [
  {
    label: "Press for the truth outright",
    check: "Insight · DC 15",
    outcome: "A crack in the story — Suspicion +1",
    tag: "check_request",
  },
  {
    label: "Offer coin for silence",
    check: "Persuasion · DC 18",
    outcome: "Bought, for now — Coin −30",
    tag: "branch_choices",
  },
  {
    label: "Threaten to call the Tidewatch",
    check: "Intimidation · DC 16",
    outcome: "Fear earns you a name — Trust −2",
    tag: "state_update",
  },
];

// ---- Pure resolvers (operate on any dataset, not just the seed) ----

const FALLBACK_SETTING: Setting = {
  id: "",
  name: "—",
  type: "",
  desc: "",
};

/** Resolve a scenario's cast + setting from id references. */
export function resolveScenario(
  scenario: Scenario,
  characters: Character[],
  settings: Setting[],
): ResolvedScenario {
  const byId = new Map(characters.map((c) => [c.id, c]));
  const cast = scenario.castIds
    .map((id) => byId.get(id))
    .filter((c): c is Character => Boolean(c));
  const setting =
    settings.find((s) => s.id === scenario.settingId) ?? FALLBACK_SETTING;
  return { ...scenario, cast, setting };
}
