import { describe, it, expect } from "vitest";
import type { GraphRelationship } from "@/lib/api";
import type {
  PersistedEvent,
  PersistedTrace,
  StatPatch,
  TurnStreamFrame,
  TurnTraceFrame,
} from "@/lib/events";
import type { SceneMessage, StatChip } from "./scene-data";
import {
  applyPresence,
  applyStatByChar,
  applyStatUpdate,
  branchOptionsToChoices,
  foldTrace,
  graphRelationshipsToRel,
  mergeFrame,
  type PresenceMap,
  rehydrateFromHistory,
  sessionIdOf,
  type TraceTurn,
} from "./turn-stream";
import type { CharacterStatusChangeEvent } from "@/lib/events";

function trace(step: string, n: number, extra: Partial<TurnTraceFrame> = {}): TurnTraceFrame {
  return { type: "trace", n, step, title: `${step} ${n}`, detail: "", data: {}, ...extra };
}

function ev(type: string, id: string, data: unknown): TurnStreamFrame {
  return {
    type,
    id,
    seq: 1,
    scenarioId: "sc",
    sessionId: "ps1",
    ts: "t",
    visibility: "public",
    data,
  } as TurnStreamFrame;
}

describe("mergeFrame", () => {
  it("accumulates narration deltas by id", () => {
    let msgs: SceneMessage[] = [];
    msgs = mergeFrame(msgs, ev("narration", "n1", { text: "Rain ", done: false }));
    msgs = mergeFrame(msgs, ev("narration", "n1", { text: "ticks.", done: true }));
    expect(msgs).toHaveLength(1);
    expect(msgs[0].kind).toBe("narrator");
    expect(msgs[0].text).toBe("Rain ticks.");
  });

  it("merges a character action then its dialogue into one beat", () => {
    let msgs: SceneMessage[] = [];
    msgs = mergeFrame(msgs, ev("character_action", "a1", { characterId: "mei", text: "Mei doesn't move." }));
    msgs = mergeFrame(msgs, ev("character_dialogue", "d1", { characterId: "mei", text: '"Coin', done: false }));
    msgs = mergeFrame(msgs, ev("character_dialogue", "d1", { characterId: "mei", text: 's easy."', done: true }));
    expect(msgs).toHaveLength(1);
    expect(msgs[0].who).toBe("mei");
    expect(msgs[0].action).toBe("Mei doesn't move.");
    expect(msgs[0].text).toBe('"Coins easy."');
  });

  it("keeps a different speaker's dialogue as a separate beat", () => {
    let msgs: SceneMessage[] = [{ kind: "char", id: "a1", who: "mei", action: "x" }];
    msgs = mergeFrame(msgs, ev("character_dialogue", "d1", { characterId: "kira", text: "Hi.", done: true }));
    expect(msgs).toHaveLength(2);
    expect(msgs[1].who).toBe("kira");
  });

  it("accumulates dialogue with no preceding action into its own beat", () => {
    let msgs: SceneMessage[] = [];
    msgs = mergeFrame(msgs, ev("character_dialogue", "d1", { characterId: "mei", text: "He", done: false }));
    msgs = mergeFrame(msgs, ev("character_dialogue", "d1", { characterId: "mei", text: "llo.", done: true }));
    expect(msgs).toHaveLength(1);
    expect(msgs[0].text).toBe("Hello.");
  });

  it("opens a char beat carrying the internal_thought (no separate bubble)", () => {
    let msgs: SceneMessage[] = [];
    msgs = mergeFrame(msgs, ev("internal_thought", "t1", { characterId: "mei", text: "Coin first." }));
    expect(msgs).toHaveLength(1);
    expect(msgs[0].kind).toBe("char");
    expect(msgs[0].who).toBe("mei");
    expect(msgs[0].thought).toBe("Coin first.");
    expect(msgs[0].text).toBeUndefined();
  });

  it("folds a thought and the following dialogue into ONE beat (think then speak)", () => {
    let msgs: SceneMessage[] = [];
    msgs = mergeFrame(msgs, ev("internal_thought", "t1", { characterId: "mei", text: "Let him sweat." }));
    msgs = mergeFrame(msgs, ev("character_dialogue", "d1", { characterId: "mei", text: "Fine.", done: true }));
    expect(msgs).toHaveLength(1);
    expect(msgs[0].kind).toBe("char");
    expect(msgs[0].thought).toBe("Let him sweat.");
    expect(msgs[0].text).toBe("Fine.");
  });

  it("folds thought → action → dialogue for one speaker into a single beat", () => {
    let msgs: SceneMessage[] = [];
    msgs = mergeFrame(msgs, ev("internal_thought", "t1", { characterId: "mei", text: "Stay calm." }));
    msgs = mergeFrame(msgs, ev("character_action", "a1", { characterId: "mei", text: "Mei leans back." }));
    msgs = mergeFrame(msgs, ev("character_dialogue", "d1", { characterId: "mei", text: "As you wish.", done: true }));
    expect(msgs).toHaveLength(1);
    expect(msgs[0].thought).toBe("Stay calm.");
    expect(msgs[0].action).toBe("Mei leans back.");
    expect(msgs[0].text).toBe("As you wish.");
  });

  it("keeps a different speaker's thought as its own beat", () => {
    let msgs: SceneMessage[] = [];
    msgs = mergeFrame(msgs, ev("internal_thought", "t1", { characterId: "mei", text: "Mine." }));
    msgs = mergeFrame(msgs, ev("internal_thought", "t2", { characterId: "kira", text: "Hers." }));
    expect(msgs).toHaveLength(2);
    expect(msgs[0].who).toBe("mei");
    expect(msgs[1].who).toBe("kira");
    expect(msgs[1].thought).toBe("Hers.");
  });

  it("ignores error frames and unknown event types", () => {
    expect(mergeFrame([], { type: "error", message: "x" })).toEqual([]);
    expect(mergeFrame([], ev("state_update", "s1", { patch: {}, stat: null }))).toEqual([]);
  });

  it("ignores trace frames (they are for the Inspector, not the transcript)", () => {
    expect(mergeFrame([], trace("director", 1))).toEqual([]);
  });
});

describe("sessionIdOf", () => {
  it("returns the envelope sessionId, null for error/trace frames", () => {
    expect(sessionIdOf(ev("narration", "n1", { text: "a", done: true }))).toBe("ps1");
    expect(sessionIdOf({ type: "error", message: "x" })).toBeNull();
    expect(sessionIdOf(trace("turn", 1))).toBeNull();
  });
});

describe("foldTrace", () => {
  it("opens a new turn group on a `turn` step and appends the rest in order", () => {
    let turns: TraceTurn[] = [];
    turns = foldTrace(turns, trace("turn", 1, { detail: "I slide the pouch." }));
    turns = foldTrace(turns, trace("director", 2));
    turns = foldTrace(turns, trace("thinking", 3));
    expect(turns).toHaveLength(1);
    expect(turns[0].label).toBe("I slide the pouch."); // player message labels the turn
    expect(turns[0].steps.map((s) => s.step)).toEqual(["turn", "director", "thinking"]);
  });

  it("starts a fresh group for each new turn", () => {
    let turns: TraceTurn[] = [];
    turns = foldTrace(turns, trace("turn", 1, { detail: "one" }));
    turns = foldTrace(turns, trace("director", 2));
    turns = foldTrace(turns, trace("turn", 1, { detail: "two" }));
    expect(turns).toHaveLength(2);
    expect(turns[1].label).toBe("two");
    expect(turns[1].steps).toHaveLength(1);
  });

  it("starts a group even if the first frame is not a `turn` step (never drops)", () => {
    const turns = foldTrace([], trace("director", 5));
    expect(turns).toHaveLength(1);
    expect(turns[0].steps[0].step).toBe("director");
  });
});

describe("applyStatUpdate", () => {
  const stat = (key: string, value: number, reason = ""): StatPatch => ({
    characterId: "c", key, value, reason,
  });

  it("updates a matching chip's value + reason (case-insensitive)", () => {
    const chips: StatChip[] = [{ label: "Suspicion", value: 2 }];
    const next = applyStatUpdate(chips, stat("suspicion", 67, "pressed"));
    expect(next).toHaveLength(1);
    expect(next[0].value === 67 && next[0].reason === "pressed").toBe(true);
  });

  it("appends a new chip for an unseen stat", () => {
    const next = applyStatUpdate([], stat("trust", 38));
    expect(next).toEqual([{ label: "Trust", value: 38, reason: "" }]);
  });
});

describe("applyStatByChar", () => {
  const stat = (characterId: string, key: string, value: number): StatPatch => ({
    characterId, key, value, reason: "",
  });

  it("buckets each stat under its own character (no cross-character collision)", () => {
    let m: Record<string, StatChip[]> = {};
    m = applyStatByChar(m, stat("maerin", "trust", 3));
    m = applyStatByChar(m, stat("aldous", "trust", -2));
    expect(m.maerin).toEqual([{ label: "Trust", value: 3, reason: "" }]);
    expect(m.aldous).toEqual([{ label: "Trust", value: -2, reason: "" }]);
  });

  it("updates a character's existing stat in place", () => {
    let m: Record<string, StatChip[]> = {};
    m = applyStatByChar(m, stat("maerin", "suspicion", 2));
    m = applyStatByChar(m, stat("maerin", "suspicion", 7));
    expect(m.maerin).toEqual([{ label: "Suspicion", value: 7, reason: "" }]);
  });
});

describe("graphRelationshipsToRel", () => {
  const rel = (over: Partial<GraphRelationship>): GraphRelationship => ({
    source: "mei", sourceName: "Mei", type: "resents", target: "beth", targetName: "Beth", reason: "", ...over,
  });

  it("maps graph edges to rail rows with the speaker's cast color", () => {
    const out = graphRelationshipsToRel([rel({ reason: "a debt" })], [{ name: "Mei", color: "#111" }]);
    expect(out[0]).toEqual({ who: "Mei", color: "#111", text: "resents Beth — a debt" });
  });

  it("falls back to a default color and omits an empty reason", () => {
    const out = graphRelationshipsToRel([rel({ type: "allied_with", reason: "" })], []);
    expect(out[0].color).toBe("#8E2B1C");
    expect(out[0].text).toBe("allied with Beth");
  });
});

describe("branchOptionsToChoices", () => {
  it("maps label/outcome to renderable choices (no check field)", () => {
    const choices = branchOptionsToChoices([{ label: "Back off", outcome: "de-escalate" }]);
    expect(choices[0].label).toBe("Back off");
    expect(choices[0].outcome).toBe("de-escalate");
    expect(choices[0].player).toBe("Back off");
    expect("check" in choices[0]).toBe(false);
  });
});

describe("rehydrateFromHistory", () => {
  function pe(type: string, seq: number, data: unknown, id = `ev${seq}`): PersistedEvent {
    return {
      type, id, seq, scenarioId: "sc", sessionId: "ps1", ts: "t",
      visibility: "public", data: data as Record<string, unknown>,
    };
  }
  function pt(step: string, turn: number, n: number, extra: Partial<PersistedTrace> = {}): PersistedTrace {
    return { turn, n, step, title: `${step}`, detail: "", data: {}, ...extra };
  }

  it("replays persisted rows into transcript, stats, and grouped trace", () => {
    const events: PersistedEvent[] = [
      pe("user_turn", 0, { text: "I slide the coin toward Mei.", directedAt: "mei" }),
      pe("internal_thought", 1, { characterId: "mei", text: "Coin first." }),
      pe("character_action", 2, { characterId: "mei", text: "doesn't touch it" }),
      pe("character_dialogue", 3, { characterId: "mei", text: '"Coin\'s easy."', done: true }),
      pe("state_update", 4, { patch: {}, stat: { characterId: "mei", key: "suspicion", value: 62, reason: "old guilt" } }),
    ];
    const traces: PersistedTrace[] = [
      pt("turn", 0, 1, { detail: "I slide the coin toward Mei." }),
      pt("lore", 0, 2),
      pt("commit", 0, 3),
    ];
    const scene = rehydrateFromHistory(events, traces);

    // The player line + the speaker's thought/action/dialogue fold into one char beat.
    expect(scene.messages[0]).toEqual({ kind: "player", text: "I slide the coin toward Mei." });
    const beat = scene.messages[1];
    expect(beat.kind).toBe("char");
    expect(beat.thought).toBe("Coin first.");
    expect(beat.action).toBe("doesn't touch it");
    expect(beat.text).toBe('"Coin\'s easy."');
    // Live stats + per-character stats rebuilt from the state_update.
    expect(scene.stats).toEqual([{ label: "Suspicion", value: 62, reason: "old guilt" }]);
    expect(scene.statsByChar.mei[0].value).toBe(62);
    // The graph/RAG trace is grouped under the turn (its player line labels the group).
    expect(scene.traceTurns).toHaveLength(1);
    expect(scene.traceTurns[0].label).toBe("I slide the coin toward Mei.");
    expect(scene.traceTurns[0].steps.map((s) => s.step)).toEqual(["turn", "lore", "commit"]);
  });

  it("skips a past branch_choices instead of resurrecting it as active", () => {
    const events: PersistedEvent[] = [
      pe("user_turn", 0, { text: "hi", directedAt: null }),
      pe("branch_choices", 1, { choices: [{ label: "Back off", outcome: "x" }] }),
    ];
    const scene = rehydrateFromHistory(events, []);
    expect(scene.messages.every((m) => m.kind !== "choices")).toBe(true);
  });

  it("folds character_status_change into presence (latest wins)", () => {
    const events: PersistedEvent[] = [
      pe("user_turn", 0, { text: "I run Mei through.", directedAt: null }),
      pe("character_status_change", 1, { characterId: "mei", status: "unconscious", reason: "", auto: true }),
      pe("character_status_change", 2, { characterId: "mei", status: "dead", reason: "", auto: true }),
      pe("character_status_change", 3, { characterId: "kira", status: "left", reason: "", auto: true }),
    ];
    const scene = rehydrateFromHistory(events, []);
    expect(scene.presenceByChar).toEqual({ mei: "dead", kira: "left" });
    // A status change is not a transcript message.
    expect(scene.messages.some((m) => m.kind === "char")).toBe(false);
  });
});

describe("applyPresence", () => {
  function statusEvent(characterId: string, status: string): CharacterStatusChangeEvent {
    return {
      type: "character_status_change", id: "ev", seq: 1, scenarioId: "sc", sessionId: "ps1",
      ts: "t", visibility: "public", data: { characterId, status: status as never, reason: "", auto: true },
    };
  }

  it("sets and overrides a character's status", () => {
    let map: PresenceMap = {};
    map = applyPresence(map, statusEvent("mei", "left"));
    expect(map).toEqual({ mei: "left" });
    map = applyPresence(map, statusEvent("kira", "dead"));
    map = applyPresence(map, statusEvent("mei", "present"));
    expect(map).toEqual({ mei: "present", kira: "dead" });
  });
});
