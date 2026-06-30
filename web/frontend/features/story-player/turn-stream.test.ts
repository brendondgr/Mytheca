import { describe, it, expect } from "vitest";
import type { TurnStreamFrame } from "@/lib/events";
import type { SceneMessage } from "./scene-data";
import { mergeFrame, sessionIdOf } from "./turn-stream";

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

  it("ignores error frames and unknown event types", () => {
    expect(mergeFrame([], { type: "error", message: "x" })).toEqual([]);
    expect(mergeFrame([], ev("state_update", "s1", { patch: {}, stat: null }))).toEqual([]);
  });
});

describe("sessionIdOf", () => {
  it("returns the envelope sessionId, null for error frames", () => {
    expect(sessionIdOf(ev("narration", "n1", { text: "a", done: true }))).toBe("ps1");
    expect(sessionIdOf({ type: "error", message: "x" })).toBeNull();
  });
});
