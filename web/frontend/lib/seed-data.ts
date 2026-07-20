import type {
  Character,
  EventTag,
  ResolvedScenario,
  Scenario,
  Setting,
  StatDefinition,
  Storyline,
} from "@/lib/types";

// The "Embergate" storyline data. The Library now loads from the backend (which
// is seeded with this same world, see web/backend/app/core/seed.py), so the
// SEED_* constants here serve two remaining roles: the Story player still reads
// them, and the Library tests use them as fixtures (via test/api-mock.ts). The
// AI_* draft pools and resolveScenario() remain in active use by the Library.

/** Fixed parchment background behind every monogram avatar. */
export const MONOGRAM_BG = "#EDE3CD";

/** Accent palette offered when forging a character (12 — the per-character cap). */
export const PALETTE = [
  "#8E2B1C",
  "#A8762A",
  "#2F7D6B",
  "#3A5A78",
  "#6B4A8A",
  "#5A534A",
  "#1F8A5B",
  "#B0506A",
  "#C56A1F",
  "#7E8A2B",
  "#2C8E8E",
  "#8E3B7A",
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
    appearance:
      "A spare, upright woman in her fifties, grey hair drawn back without a single loose strand. Ink-stained fingers, a merchant's good coat gone slightly threadbare at the cuffs, and eyes that price a room before they greet it.",
    background:
      "Born to a harbor-ledger family that lost everything in the last blockade, Maerin rebuilt it ledger by ledger until she held half the docks' debts. The Saltworn is hers in all but name; she lets others believe otherwise.",
    personality:
      "Patient to the point of cruelty. She never gambles — she waits for the odds to walk to her. Loyalty is a line item; mercy is a favor she expects repaid with interest.",
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
    appearance:
      "A soft-bodied monk in his forties, robes salt-stained at the hem, hands forever worrying a string of cheap prayer-beads. A burn scar climbs one wrist into his sleeve, which he keeps tugged down.",
    background:
      "Aldous tended the warehouse chapel that fed the dock's poor, until the night the fire took the stores — and three sleeping dockhands with them. The Order sent him back to serve where he sinned, never knowing the lantern was his.",
    personality:
      "Gentle, anxious, and stubborn in the way frightened people are. He apologizes before he is accused and confesses to everything except the one thing that matters.",
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
    appearance:
      "Wiry and quick, late twenties, dark hair cropped short for practicality and a sailor's coat two sizes too big. Knuckles scarred, a knife she doesn't hide, and a grin she uses like a tool.",
    background:
      "Dock-born and dock-raised, Wren has run cargo, contraband, and the occasional message no one wanted traced. She has been almost-free of Embergate four times; the harbor keeps finding new ways to charge her rent.",
    personality:
      "Sardonic, fast-talking, loyal right up to the price where loyalty stops paying. She likes you more than she'll admit and trusts you exactly as far as her last empty purse.",
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
    appearance:
      "Broad and straight-backed in a Tidewatch uniform kept immaculate against all the harbor's grime, greying at the temples. A old duelling scar along the jaw; hands that rest near, but never on, his sword.",
    background:
      "Doran took the Captaincy when the last one drowned drunk, and has spent a decade trying to scrub the rot out of an institution that runs on it. Every clean arrest he makes, his brother's market grows another stall.",
    personality:
      "Rigid, dutiful, honorable to a fault that everyone but him can see. He believes the law is a wall against the tide; he hasn't yet admitted the tide is family.",
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
    appearance:
      "Ageless and pale, draped in salt-crusted grey, eyes filmed the milky white of sea-glass. She moves slowly, surely, as if the floor were a tide she has already read.",
    background:
      "The Oracle of Salt has read the harbor's fortunes for longer than anyone living recalls. Sailors leave coin at her sanctum before every voyage; half of them sail anyway against her counsel, and drown proving her right.",
    personality:
      "Serene, cryptic, and kind in a way that frightens people. She speaks in tides and rarely answers the question asked — only the one you should have.",
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
    appearance:
      "A slab of a man, scarred and shaven-headed, with a cudgel worn smooth by use and a coat that has stopped more than one knife. He stands a careful distance from any railing that overlooks the water.",
    background:
      "Grimm has been muscle for every crew that could meet his price and a few that only thought they could. No one knows where he's from; the harbor assumes he washed up, which he would not find funny.",
    personality:
      "Brutal, brief, and entirely transactional — until the deck pitches or the tide comes in, and the fear he buries under all that menace surfaces in his eyes.",
  },
];

export const SEED_SETTINGS: Setting[] = [
  {
    id: "saltworn",
    name: "The Saltworn Tavern",
    type: "Social Hub",
    desc: "Lamplit and low-beamed — every secret here has a price.",
    atmosphere:
      "Smoke-darkened beams, the smell of tallow and spilled ale, rain ticking at the shutters. Conversation drops a register whenever the door opens, then resumes a beat too smoothly.",
    features:
      "A long ledger-table where Maerin holds court, a back stair to rooms that aren't rented, and a fireplace built over an older, bricked-up door no one mentions.",
    currentState:
      "Past midnight, half-full, a storm holding the usual crowd indoors. Maerin's table is occupied; the Captain's man has been nursing the same drink by the door for an hour.",
  },
  {
    id: "harbor",
    name: "Embergate Harbor",
    type: "Exploration",
    desc: "Fog, brine, and the groan of a hundred moored hulls.",
    atmosphere:
      "Wet rope and rotting fish, gulls arguing over the tideline, fog so thick the far quay is only a rumor of lamplight. Every plank underfoot is slick and complaining.",
    features:
      "The harbor master's counting-house, a crane that hasn't turned in years, and the north dock where the night cargo comes in without a manifest.",
    currentState:
      "Low tide, before dawn. The watch has changed and the new shift hasn't found its lanterns yet — a narrow, cold window where the docks belong to no one.",
  },
  {
    id: "keep",
    name: "Tidewatch Keep",
    type: "Fortress",
    desc: "The guard's stone fist clenched over the bay.",
    atmosphere:
      "Cold stone sweating with sea-damp, the clack of drilled boots, torchlight that never quite reaches the corners. Sound carries here — the keep was built to overhear.",
    features:
      "A signal beacon over the bay, a records vault of every ship's papers, and cells cut below the waterline that flood a little at every high tide.",
    currentState:
      "Tense and under-staffed. Half the garrison is loyal to the Captain, half to whoever pays better; both halves are pretending they haven't noticed the other.",
  },
  {
    id: "market",
    name: "The Drowned Market",
    type: "Black Market",
    desc: "Below the tideline, where nothing is illegal.",
    atmosphere:
      "A vaulted cellar that breathes with the sea, lantern-light swimming on standing water, voices kept low and quick. Everything for sale and nothing on a shelf.",
    features:
      "Stalls that pack up in a heartbeat, a money-changer who fences as a sideline, and a tide-gate that floods the lower vault when the bells ring the turn.",
    currentState:
      "Open for the night's trade, busy and wary. The tide is two hours from turning; everyone here is counting bells, including the people who shouldn't be.",
  },
  {
    id: "sanctum",
    name: "The Oracle's Sanctum",
    type: "Sacred",
    desc: "Salt-circles and the hush before a truth.",
    atmosphere:
      "Cold, still air that tastes of brine, salt crusting the stone in pale rings, a quiet so complete that your own pulse becomes a sound. Candle-flames stand without a flicker.",
    features:
      "Concentric salt-circles worn into the floor, a basin of seawater the Oracle reads, and an alcove of votive coins left by sailors who never came back for them.",
    currentState:
      "Lit and waiting, as if she expected you. The Oracle is present and unhurried; the salt-circles are freshly drawn, which she does for no one without reason.",
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

// The storyline is the top-level container (docs/documentation.md): it owns its
// own cast, places, and scenarios. We ship one seeded storyline ("Embergate");
// the header switcher can create more, and switching swaps the working set.
export const SEED_STORYLINES: Storyline[] = [
  {
    id: "embergate",
    title: "Embergate",
    genre: "Maritime Intrigue",
    tagline: "A rotting harbor town where every secret has a price.",
    symbol: "◆",
    symbolColor: "#C8862A",
    characters: SEED_CHARACTERS,
    settings: SEED_SETTINGS,
    scenarios: SEED_SCENARIOS,
  },
];

// The Embergate world's universal stat schema (mirrors web/backend/app/core/seed.py
// `_STATS` + content/stats/*.md). The Library loads these from the backend; the
// Story player reads them here so the in-scene director rail can show the real
// stat definitions + labeled bands without a backend round-trip.
export const SEED_STAT_DEFS: StatDefinition[] = [
  {
    key: "health",
    displayName: "Health",
    description: "Physical condition and vitality.",
    min: 0,
    max: 100,
    default: 100,
    visibility: "public",
    guidance: "stats/health.md",
    appliesTo: [],
    bands: [
      { min: 0, max: 20, label: "Nearly dead" },
      { min: 21, max: 40, label: "Badly hurt — needs to heal" },
      { min: 41, max: 80, label: "Wounded but holding" },
      { min: 81, max: 100, label: "Very healthy" },
    ],
  },
  {
    key: "suspicion",
    displayName: "Suspicion",
    description: "How wary the authorities and factions are of you.",
    min: 0,
    max: 10,
    default: 0,
    visibility: "public",
    guidance: "stats/suspicion.md",
    appliesTo: [],
    bands: [
      { min: 0, max: 3, label: "Unnoticed" },
      { min: 4, max: 7, label: "Watched" },
      { min: 8, max: 10, label: "Hunted" },
    ],
  },
  {
    key: "trust",
    displayName: "Trust",
    description: "Personal standing with your close allies.",
    min: -5,
    max: 5,
    default: 0,
    visibility: "public",
    guidance: "stats/trust.md",
    appliesTo: [],
    bands: [
      { min: -5, max: -3, label: "Betrayed" },
      { min: -2, max: -1, label: "Skeptical" },
      { min: 0, max: 0, label: "Neutral" },
      { min: 1, max: 2, label: "Earned trust" },
      { min: 3, max: 5, label: "Deep trust" },
    ],
  },
  {
    key: "patience",
    displayName: "Patience",
    description: "How much forbearance you have left before you act rashly.",
    min: 0,
    max: 10,
    default: 5,
    visibility: "public",
    guidance: "stats/patience.md",
    appliesTo: [],
    bands: [
      { min: 0, max: 2, label: "At the limit" },
      { min: 3, max: 5, label: "Holding on" },
      { min: 6, max: 8, label: "Composed" },
      { min: 9, max: 10, label: "Serene" },
    ],
  },
];

// ---- Agentic "draft with Mytheca" pools (faked generation, no model call) ----

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
