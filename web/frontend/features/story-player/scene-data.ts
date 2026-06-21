import type { ResolvedScenario } from "@/lib/types";

// Seed for a playable scene. The "Embergate Conspiracy" is fully scripted to
// match the reference; any other scenario gets a believable generic opening
// built from its cast + branches. No model calls — interactions are local.

export type SceneMessageKind =
  | "narrator"
  | "char"
  | "player"
  | "check"
  | "choices";

export interface SceneMessage {
  kind: SceneMessageKind;
  who?: string;
  action?: string;
  text?: string;
  check?: string;
  roll?: number;
  result?: "Success" | "Failure";
}

export interface SceneChoice {
  id: string;
  label: string;
  outcome: string;
  check: string;
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
  { kind: "check", check: "Insight · DC 15", roll: 17, result: "Success", text: "You read the stillness in Maerin's hands. Her composure is rehearsed — she is performing calm for someone. Her eyes flick, just once, to the Captain by the door." },
  { kind: "narrator", text: "By the door, Captain Doran Hale has not touched his drink. He has been watching the ledger in Maerin's hands the entire time." },
  { kind: "char", who: "doran", text: "Voss. The harbor master's ledger is missing three pages. You wouldn't happen to know where they went." },
  { kind: "char", who: "maerin", action: "to you, quieter now", text: "Choose your next words carefully. We can both walk out of here richer — or you can hand me to the Captain and learn nothing at all." },
  { kind: "choices" },
];

const EMBERGATE_CHOICES: SceneChoice[] = [
  { id: "confront", label: "Confront Maerin about the Captain", outcome: "Press the fear you just saw — Suspicion +2", check: "Insight · DC 15", player: "You're afraid of him, aren't you? The good Captain by the door.", follow: { who: "maerin", action: "her smile thins", text: "Afraid is a strong word. Cautious. As you should be." }, suspicion: 2, tension: 8 },
  { id: "bargain", label: "Bargain — silence for the ledger", outcome: "Trade your discretion for the routes — Trust −1", check: "Persuasion · DC 20", player: "Give me the routes, and the Captain never hears your name from me.", follow: { who: "maerin", action: "considers", text: "A merchant's offer. I almost like you. Almost." }, trust: -1, tension: 4 },
  { id: "expose", label: "Expose her to Captain Hale", outcome: "Turn the room — his favour +3", check: "Deception · DC 15", player: "Captain! The pages you're missing — they're in her ledger right now.", follow: { who: "doran", action: "steps forward", text: "Is that so. Voss — the book. On the table. Slowly." }, tension: 12 },
];

function genericScene(scenario: ResolvedScenario): SceneSeed {
  const cast = scenario.cast;
  const messages: SceneMessage[] = [
    { kind: "narrator", text: scenario.opening || "The scene opens. Every eye finds you." },
  ];
  cast.slice(0, 2).forEach((c, i) => {
    messages.push({
      kind: "char",
      who: c.id,
      action: i === 0 ? undefined : "watching you",
      text:
        i === 0
          ? "So you've come after all. Sit — let's see what you're made of."
          : "Mind yourself here. Not everyone at this table wishes you well.",
    });
  });
  messages.push({ kind: "choices" });

  const choices: SceneChoice[] = scenario.branches.map((b, i) => ({
    id: `b${i}`,
    label: b.label,
    outcome: b.outcome,
    check: b.check,
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
      text: `— ${c.secret.replace(/\.$/, "").toLowerCase()}.`,
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
