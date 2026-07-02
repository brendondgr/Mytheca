import { describe, it, expect } from "vitest";
import type { GraphRelationship } from "@/lib/api";
import type { StatPatch, TurnStreamFrame, TurnTraceFrame } from "@/lib/events";
import type { SceneMessage, StatChip } from "./scene-data";
import {
  applyStatUpdate,
  branchOptionsToChoices,
  foldTrace,
  graphRelationshipsToRel,
  mergeFrame,
  sessionIdOf,
  type TraceTurn,
} from "./turn-stream";

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
