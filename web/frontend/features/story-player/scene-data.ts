import type { ResolvedScenario } from "@/lib/types";

// Seed for a playable scene. The "Embergate Conspiracy" is fully scripted to
// match the reference; any other scenario gets a believable generic opening
// built from its cast + branches. No model calls — interactions are local.

/**
 * `direction` is the player's own steer on a turn where they said nothing out loud. It is
 * deliberately a separate kind from `player`: a direction was never spoken in the scene, so
 * rendering it as a speech bubble would put words in the character's mouth that nobody in
 * the story ever heard.
 */
export type SceneMessageKind =
  | "narrator"
  | "char"
  | "player"
  | "direction"
  | "choices"
  | "image";

/** A picture of the moment, from a `scene_image` event (the Create image action). */
export interface SceneImage {
  /** Relative `/media/moments/…` path — resolve with `mediaUrl` before rendering. */
  url: string;
  /** One plain-English line describing the picture; the image's alt text. */
  caption: string;
  /** The ComfyUI prompt that produced it (shown behind a disclosure in the lightbox). */
  prompt: string;
}

export interface SceneMessage {
  kind: SceneMessageKind;
  who?: string;
  action?: string;
  /**
   * The beat's prose — and, on a `choices` beat, the planner's question to the player
   * (empty for the ordinary end-of-turn follow-ups, which are offered rather than asked).
   */
  text?: string;
  /** Set on `kind: "image"` beats — the rendered picture and its caption. */
  image?: SceneImage;
  /**
   * A character's private thinking, folded into the SAME beat as their speech: it renders
   * muted, between the name and the spoken bubble. Populated from an `internal_thought`
   * event that precedes the speaker's action/dialogue.
   */
  thought?: string;
  /**
   * Streamed-event id of the `thought` above. The thought and the spoken line are two
   * separate events folded into one beat, so the beat's own `id` (the dialogue's) cannot
   * be used to accumulate the thought's deltas — it needs its own.
   */
  thoughtId?: string;
  /**
   * This beat has been announced but nothing has been written into it yet — the speaker
   * is chosen and the model is working. It holds the character's place in the transcript
   * so the thought → speech sequence fills in one stable spot, and so the wait has a
   * location instead of only a floating status pill.
   */
  pending?: boolean;
  /** Streamed-event id — used to accumulate delta chunks of narration/dialogue. */
  id?: string;
  /**
   * Player POV: this is a `char` beat the PLAYER authored (they were speaking AS `who`).
   * Rendered on the player's side of the transcript but wearing the character's identity
   * (`PlayerAsCharacterMessage`). Set on the optimistic bubble and on rehydrate from a
   * `user_turn` row with `data.pov`.
   */
  fromPlayer?: boolean;
  /**
   * How many versions of this beat exist and which is showing, when it has been re-rolled.
   * Absent for a beat with a single take — the pager is not rendered at all then.
   */
  takes?: { count: number; active: number };
  /**
   * Context documents this player turn carried as reference. Persisted on the `user_turn`
   * row, so a resumed scene can show what a past turn was given rather than leaving the
   * player to remember.
   */
  taggedDocIds?: string[];
}

// A branch fork the player can pick — no dice/checks (D11): label + a narrative-
// direction outcome. Selecting one submits a real turn.
export interface SceneChoice {
  id: string;
  label: string;
  outcome: string;
  player: string;
  follow: { who: string; action?: string; text: string };
  suspicion?: number;
  trust?: number;
  tension?: number;
}

export interface StatChip {
  label: string;
  /** signed current value, e.g. 2 → "+2". */
  value: number;
  /** "neutral" colors by --ink-soft; positive/negative tint accent/green. */
  kind?: "neutral" | "good" | "bad";
  /** Free-text audit trail from a state_update (why the value moved). */
  reason?: string;
}

export interface Relationship {
  who: string;
  color: string;
  text: string;
}

export interface SceneSeed {
  messages: SceneMessage[];
  choices: SceneChoice[];
  tension: number;
  stats: StatChip[];
  relationships: Relationship[];
  /** turn order: ids + the literal "You". */
  turnOrder: string[];
}

const EMBERGATE_MESSAGES: SceneMessage[] = [
  { kind: "narrator", text: "Lamplight gutters across the Saltworn's long tables. Rain ticks against the shutters. Maerin Voss has not looked up from her ledger once — which is how you know she has already seen you walk in." },
  { kind: "char", who: "maerin", text: "You're late. The tide doesn't wait, and neither do I. Sit — before the whole room wonders why you're standing." },
  { kind: "char", who: "wren", action: "leans in, low", text: "Careful. She counts everything — including the seconds you waste. And she never forgets a debt." },
  { kind: "player", text: "I'm not here to waste your time, Maerin. I'm here about the salt moving through the north dock." },
  { kind: "narrator", text: "A hush settles over the table. Across from you, Brother Aldous's knuckles whiten around his cup." },
  { kind: "char", who: "aldous", action: "barely above a whisper", text: "Please — whatever you've heard, the fire at the warehouse was an accident. I never meant for anyone to—" },
  { kind: "char", who: "maerin", action: "cutting in", text: "Brother. Breathe. No one at this table has accused you of anything… yet. Let our guest speak." },
  { kind: "narrator", text: "By the door, Captain Doran Hale has not touched his drink. He has been watching the ledger in Maerin's hands the entire time." },
  { kind: "char", who: "doran", text: "Voss. The harbor master's ledger is missing three pages. You wouldn't happen to know where they went." },
  { kind: "char", who: "maerin", action: "to you, quieter now", text: "Choose your next words carefully. We can both walk out of here richer — or you can hand me to the Captain and learn nothing at all." },
  { kind: "choices" },
];

const EMBERGATE_CHOICES: SceneChoice[] = [
  { id: "confront", label: "Confront Maerin about the Captain", outcome: "Press the fear you just saw", player: "You're afraid of him, aren't you? The good Captain by the door.", follow: { who: "maerin", action: "her smile thins", text: "Afraid is a strong word. Cautious. As you should be." }, suspicion: 2, tension: 8 },
  { id: "bargain", label: "Bargain — silence for the ledger", outcome: "Trade your discretion for the routes", player: "Give me the routes, and the Captain never hears your name from me.", follow: { who: "maerin", action: "considers", text: "A merchant's offer. I almost like you. Almost." }, trust: -1, tension: 4 },
  { id: "expose", label: "Expose her to Captain Hale", outcome: "Turn the room against her", player: "Captain! The pages you're missing — they're in her ledger right now.", follow: { who: "doran", action: "steps forward", text: "Is that so. Voss — the book. On the table. Slowly." }, tension: 12 },
];

function genericScene(scenario: ResolvedScenario): SceneSeed {
  const cast = scenario.cast;
  // Only the narrator opens the scene — no character speaks unprompted at the start
  // (feedback #1). Characters enter once the player takes their first action.
  const messages: SceneMessage[] = [
    { kind: "narrator", text: scenario.opening || "The scene opens. Every eye finds you." },
  ];
  messages.push({ kind: "choices" });

  const choices: SceneChoice[] = scenario.branches.map((b, i) => ({
    id: `b${i}`,
    label: b.label,
    outcome: b.outcome,
    player: b.label,
    follow: {
      who: cast[i % Math.max(cast.length, 1)]?.id ?? "",
      text: b.outcome,
    },
    tension: 6,
  }));

  return {
    messages,
    choices,
    tension: 50,
    stats: [
      { label: "Suspicion", value: 0, kind: "neutral" },
      { label: `${cast[0]?.name ?? "Their"} trust`.replace(/ trust$/, "'s trust"), value: 0, kind: "neutral" },
    ],
    relationships: cast.slice(0, 3).map((c) => ({
      who: c.name.split(",")[0].split(" ")[0],
      color: c.color,
      text: c.secret
        ? `— ${c.secret.replace(/\.$/, "").toLowerCase()}.`
        : "— keeps their own counsel.",
    })),
    turnOrder: ["You", ...cast.map((c) => c.id)],
  };
}

/** Build the initial scene for a scenario (scripted for Embergate). */
export function buildScene(scenario: ResolvedScenario): SceneSeed {
  if (scenario.id !== "embergate") return genericScene(scenario);
  return {
    messages: EMBERGATE_MESSAGES.map((m) => ({ ...m })),
    choices: EMBERGATE_CHOICES.map((c) => ({ ...c })),
    tension: 68,
    stats: [
      { label: "Suspicion", value: 2, kind: "neutral" },
      { label: "Maerin's Trust", value: 0, kind: "neutral" },
      { label: "Hale's Favour", value: 0, kind: "neutral" },
    ],
    relationships: [
      { who: "Maerin", color: "#C8543E", text: "— secretly answers to the Drowned Court." },
      { who: "Aldous", color: "#A8762A", text: "— hides that he set the warehouse fire." },
      { who: "Doran", color: "#5A7CA0", text: "— his own brother runs the black market." },
    ],
    turnOrder: ["You", "wren", "maerin", "doran", "aldous"],
  };
}

export function tensionLabel(tension: number): string {
  if (tension > 80) return "Breaking point";
  if (tension > 55) return "Rising — the room is taut";
  if (tension > 30) return "Simmering";
  return "Calm";
}
