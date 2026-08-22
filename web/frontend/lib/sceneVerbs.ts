/**
 * The direction verbs — the one-tap phrasings on the direction row.
 *
 * The owner's complaint about the old five-button row was that it is "a little boring and
 * users don't even look at it half the time". Two things are wrong with a flat row of
 * labels, and both are fixed here rather than by adding more buttons.
 *
 * **A verb gives you a sentence to argue with, not a command to fire.** Each entry owns a
 * `text` distinct from its `label`: tapping *Escalate* writes "Something makes this worse —
 * push the moment past where it was going" into the direction box, where the player edits
 * it. The label is the shortcut; the phrasing is the direction.
 *
 * **A verb that cannot mean anything is not offered.** *Someone arrives* with nobody left in
 * the world, *Move the scene* in a storyline with one place, *End the scene* on the first
 * turn — each of those is a button that does nothing, and a row of them is exactly what
 * trains a player to stop reading the row. `availableVerbs` applies those gates, and it is a
 * pure function so the gating is testable without a DOM.
 */

/** The four groups, in display order. */
export const VERB_GROUPS = ["pace", "tone", "event", "exit"] as const;
export type VerbGroup = (typeof VERB_GROUPS)[number];

export const VERB_GROUP_LABELS: Record<VerbGroup, string> = {
  pace: "Pace",
  tone: "Tone",
  event: "Event",
  exit: "Exit",
};

export interface SceneVerb {
  id: string;
  group: VerbGroup;
  /** The chip's short name. */
  label: string;
  /** What is written into the direction target — a sentence, not a command. */
  text: string;
  /**
   * Why this verb might not be offered.
   *
   * - `absentCast` — needs someone in the world who is not in the scene.
   * - `manySettings` — needs somewhere else to go.
   * - `midScene` — needs the scene to have got going (see {@link MID_SCENE_TURNS}).
   */
  requires?: "absentCast" | "manySettings" | "midScene";
  /** Expands into a per-character submenu rather than inserting text directly. */
  expands?: "cast";
}

/** How many player turns before ending or wrapping up is a sensible thing to offer. */
export const MID_SCENE_TURNS = 3;

export const BUILT_IN_VERBS: SceneVerb[] = [
  // --- Pace ---
  {
    id: "push",
    group: "pace",
    label: "Push it forward",
    text: "Move this along — get to the next thing that actually happens.",
  },
  {
    id: "slow",
    group: "pace",
    label: "Slow down",
    text: "Stay in this moment. Let it breathe before anything else happens.",
  },
  {
    id: "skip",
    group: "pace",
    label: "Skip ahead",
    text: "Skip past the rest of this and pick up once it has played out.",
  },
  {
    id: "later",
    group: "pace",
    label: "Cut to later",
    text: "Cut forward in time — later the same day, after this has settled.",
  },
  // --- Tone ---
  {
    id: "escalate",
    group: "tone",
    label: "Escalate",
    text: "Something makes this worse — push the moment past where it was going.",
  },
  {
    id: "calm",
    group: "tone",
    label: "Calm it down",
    text: "The tension comes off this. Someone gives ground.",
  },
  {
    id: "warm",
    group: "tone",
    label: "Turn it warm",
    text: "Let some warmth in — someone softens, or admits something kind.",
  },
  {
    id: "cold",
    group: "tone",
    label: "Turn it cold",
    text: "The warmth goes out of this. Someone withdraws.",
  },
  // --- Event ---
  {
    id: "arrives",
    group: "event",
    label: "Someone arrives",
    // Never inserted directly: it opens a submenu of the people who could actually walk in,
    // and choosing one raises a request the player still has to approve.
    text: "",
    requires: "absentCast",
    expands: "cast",
  },
  {
    id: "interrupt",
    group: "event",
    label: "An interruption",
    text: "Something interrupts this before it can finish.",
  },
  {
    id: "breaks",
    group: "event",
    label: "Something breaks",
    text: "Something gives way — an object, a plan, or someone's composure.",
  },
  {
    id: "revelation",
    group: "event",
    label: "A revelation",
    text: "Something comes out that changes how this looks.",
  },
  // --- Exit ---
  {
    id: "wrap",
    group: "exit",
    label: "Wrap this up",
    text: "Bring this to a close — settle what is open and let it land.",
    requires: "midScene",
  },
  {
    id: "end",
    group: "exit",
    label: "End the scene",
    text: "End the scene here, on a line that closes it.",
    requires: "midScene",
  },
  {
    id: "move",
    group: "exit",
    label: "Move the scene",
    text: "Move this somewhere else — the scene continues in a new place.",
    requires: "manySettings",
  },
];

/** A scene's own verb as authored: no id, since the author writes only the three fields. */
export type AuthoredVerb = Omit<SceneVerb, "id">;

export interface VerbContext {
  /** People in the world who are not in this scene — what "Someone arrives" needs. */
  absentCast: { id: string; name: string }[];
  /** How many places the storyline has — "Move the scene" needs somewhere to go. */
  settingCount: number;
  /** Player turns taken in this session, gating the Exit group. */
  playerTurns: number;
}

/**
 * The verbs worth offering right now, in group order, with any scenario-authored verbs
 * appended to their group after the built-ins.
 *
 * Authored verbs carry no `requires` — the author wrote them for this scene, so gating them
 * on generic conditions would second-guess someone who knows more about the scene than this
 * function does.
 */
export function availableVerbs(
  ctx: VerbContext,
  authored: AuthoredVerb[] = [],
): SceneVerb[] {
  // Authored verbs arrive without an id (the author writes a label, a group and a phrasing).
  // One is derived here so the bar has a stable React key and the roving index is unambiguous
  // — prefixed, so an authored verb can never collide with a built-in id.
  const custom: SceneVerb[] = authored
    .filter((v) => v.label?.trim() && v.text?.trim())
    .map((v, i) => ({ ...v, id: `authored-${i}-${v.label}` }));
  const allowed = (verb: SceneVerb): boolean => {
    if (verb.requires === "absentCast") return ctx.absentCast.length > 0;
    if (verb.requires === "manySettings") return ctx.settingCount > 1;
    if (verb.requires === "midScene") return ctx.playerTurns >= MID_SCENE_TURNS;
    return true;
  };
  const out: SceneVerb[] = [];
  for (const group of VERB_GROUPS) {
    out.push(...BUILT_IN_VERBS.filter((v) => v.group === group && allowed(v)));
    out.push(...custom.filter((v) => v.group === group));
  }
  return out;
}
