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
  applyActivity,
  applyCharacterActivity,
  applyTurnStatus,
  IDLE_TURN_STATUS,
  type TurnStatus,
  type ActivityEntry,
  type CharacterActivity,
  applyPresence,
  applyStatByChar,
  applyStatUpdate,
  baselineStatsByChar,
  branchOptionsToChoices,
  foldTrace,
  graphRelationshipsToRel,
  latestContextTokens,
  latestPov,
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

  it("accumulates a streamed thought instead of replacing it", () => {
    // The thought delta-streams now — it is usually the first thing a turn can show —
    // so chunks must append. Replacing would leave only the final fragment on screen.
    let msgs: SceneMessage[] = [];
    msgs = mergeFrame(msgs, ev("internal_thought", "t1", { characterId: "mei", text: "He is ", done: false }));
    msgs = mergeFrame(msgs, ev("internal_thought", "t1", { characterId: "mei", text: "testing me.", done: true }));
    expect(msgs).toHaveLength(1);
    expect(msgs[0].thought).toBe("He is testing me.");
  });

  it("folds a streamed thought and streamed dialogue into ONE beat", () => {
    let msgs: SceneMessage[] = [];
    msgs = mergeFrame(msgs, ev("internal_thought", "t1", { characterId: "mei", text: "Lie.", done: false }));
    msgs = mergeFrame(msgs, ev("internal_thought", "t1", { characterId: "mei", text: " Calmly.", done: true }));
    msgs = mergeFrame(msgs, ev("character_dialogue", "d1", { characterId: "mei", text: "I was ", done: false }));
    msgs = mergeFrame(msgs, ev("character_dialogue", "d1", { characterId: "mei", text: "home.", done: true }));
    expect(msgs).toHaveLength(1);
    expect(msgs[0].thought).toBe("Lie. Calmly.");
    expect(msgs[0].text).toBe("I was home.");
  });

  it("keeps two speakers' streamed thoughts in separate beats", () => {
    let msgs: SceneMessage[] = [];
    msgs = mergeFrame(msgs, ev("internal_thought", "t1", { characterId: "mei", text: "A", done: false }));
    msgs = mergeFrame(msgs, ev("character_dialogue", "d1", { characterId: "mei", text: "Hi.", done: true }));
    msgs = mergeFrame(msgs, ev("internal_thought", "t2", { characterId: "kira", text: "B", done: false }));
    msgs = mergeFrame(msgs, ev("internal_thought", "t2", { characterId: "kira", text: "C", done: true }));
    expect(msgs).toHaveLength(2);
    expect(msgs[0].thought).toBe("A");
    expect(msgs[1].thought).toBe("BC");
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

  it("appends a scene_image as its own beat, in stream order", () => {
    let msgs: SceneMessage[] = [];
    msgs = mergeFrame(msgs, ev("character_dialogue", "d1", { characterId: "mei", text: '"Sit."', done: true }));
    msgs = mergeFrame(
      msgs,
      ev("scene_image", "img1", {
        url: "/media/moments/abc.webp",
        prompt: "two figures at a lamplit table, wide landscape composition",
        negative: "text",
        caption: "Two figures at a lamplit table.",
        characterIds: ["mei"],
      }),
    );
    expect(msgs).toHaveLength(2);
    expect(msgs[1].kind).toBe("image");
    expect(msgs[1].image).toEqual({
      url: "/media/moments/abc.webp",
      caption: "Two figures at a lamplit table.",
      prompt: "two figures at a lamplit table, wide landscape composition",
    });
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

describe("baselineStatsByChar", () => {
  it("builds a per-character StatChip map from persisted starting values", () => {
    const base = baselineStatsByChar({
      maerin: { trust: 70, suspicion: 10 },
      aldous: { trust: 20 },
    });
    expect(base.maerin).toEqual(
      expect.arrayContaining([
        { label: "Trust", value: 70, reason: "" },
        { label: "Suspicion", value: 10, reason: "" },
      ]),
    );
    expect(base.aldous).toEqual([{ label: "Trust", value: 20, reason: "" }]);
  });

  it("returns an empty map for no characters, and no bucket for a character with no values", () => {
    expect(baselineStatsByChar({})).toEqual({});
    expect(baselineStatsByChar({ maerin: {} })).toEqual({});
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

  it("replays a persisted scene_image back into its place in the transcript", () => {
    const events: PersistedEvent[] = [
      pe("user_turn", 0, { text: "hi", directedAt: null }),
      pe("character_dialogue", 1, { characterId: "mei", text: '"Sit."', done: true }),
      pe("scene_image", 2, {
        url: "/media/moments/abc.webp",
        prompt: "two figures at a lamplit table",
        negative: "text",
        caption: "Two figures at a lamplit table.",
        characterIds: ["mei"],
      }),
    ];
    const scene = rehydrateFromHistory(events, []);
    expect(scene.messages.map((m) => m.kind)).toEqual(["player", "char", "image"]);
    expect(scene.messages[2].image?.url).toBe("/media/moments/abc.webp");
  });

  it("layers persisted deltas on top of a supplied initial statsByChar baseline", () => {
    const events: PersistedEvent[] = [
      pe("user_turn", 0, { text: "hi", directedAt: null }),
      pe("state_update", 1, { patch: {}, stat: { characterId: "mei", key: "trust", value: 55, reason: "warmed up" } }),
    ];
    const base = { mei: [{ label: "Trust", value: 40, reason: "" }, { label: "Suspicion", value: 5, reason: "" }] };
    const scene = rehydrateFromHistory(events, [], base);
    // The touched stat (trust) reflects the persisted delta...
    expect(scene.statsByChar.mei).toEqual(
      expect.arrayContaining([
        { label: "Trust", value: 55, reason: "warmed up" },
        { label: "Suspicion", value: 5, reason: "" },
      ]),
    );
    // ...while the untouched baseline entry (suspicion) survives unchanged.
    const suspicion = scene.statsByChar.mei.find((c) => c.label === "Suspicion");
    expect(suspicion?.value).toBe(5);
  });

  it("defaults to an empty statsByChar baseline when none is supplied", () => {
    const scene = rehydrateFromHistory([pe("user_turn", 0, { text: "hi", directedAt: null })], []);
    expect(scene.statsByChar).toEqual({});
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

  it("rehydrates a POV user_turn as a right-side player-authored character beat", () => {
    const events: PersistedEvent[] = [
      pe("user_turn", 0, { text: "I have nothing to say to you.", directedAt: null, pov: "mei" }),
      pe("character_dialogue", 1, { characterId: "kira", text: '"Then leave."', done: true }),
    ];
    const scene = rehydrateFromHistory(events, []);
    // The player's line wears the POV character's identity and renders on the player's side.
    expect(scene.messages[0]).toEqual({
      kind: "char",
      who: "mei",
      fromPlayer: true,
      text: "I have nothing to say to you.",
    });
    // The AI's reaction stays an ordinary (left-side) character beat — not player-authored.
    expect(scene.messages[1].kind).toBe("char");
    expect(scene.messages[1].who).toBe("kira");
    expect(scene.messages[1].fromPlayer).toBeUndefined();
  });

  it("keeps a user_turn without pov as a plain left-side player beat", () => {
    const scene = rehydrateFromHistory([pe("user_turn", 0, { text: "hi", directedAt: null })], []);
    expect(scene.messages[0]).toEqual({ kind: "player", text: "hi" });
  });
});

describe("latestPov", () => {
  function pe(type: string, seq: number, data: unknown, id = `ev${seq}`): PersistedEvent {
    return {
      type, id, seq, scenarioId: "sc", sessionId: "ps1", ts: "t",
      visibility: "public", data: data as Record<string, unknown>,
    };
  }

  it("returns the pov of the most recent user_turn", () => {
    const events: PersistedEvent[] = [
      pe("user_turn", 0, { text: "a", pov: "mei" }),
      pe("character_dialogue", 1, { characterId: "kira", text: "x", done: true }),
      pe("user_turn", 2, { text: "b", pov: "kira" }), // most recent wins
    ];
    expect(latestPov(events)).toBe("kira");
  });

  it("returns null when the latest user_turn has no pov (guide/narrator line)", () => {
    const events: PersistedEvent[] = [
      pe("user_turn", 0, { text: "a", pov: "mei" }),
      pe("user_turn", 1, { text: "b", directedAt: null }), // no pov → back to narrator
    ];
    expect(latestPov(events)).toBeNull();
  });

  it("returns null when there are no user_turn rows", () => {
    expect(latestPov([pe("character_dialogue", 0, { characterId: "mei", text: "x", done: true })])).toBeNull();
    expect(latestPov([])).toBeNull();
  });
});

describe("latestContextTokens", () => {
  const t = (step: string, n: number, data: Record<string, unknown> = {}): PersistedTrace => ({
    turn: 0, n, step, title: step, detail: "", data,
  });

  it("returns the last `context` step's promptTokens", () => {
    const traces: PersistedTrace[] = [
      t("turn", 1),
      t("context", 2, { promptTokens: 3000 }),
      t("commit", 3),
      t("context", 4, { promptTokens: 7200 }), // most recent wins
    ];
    expect(latestContextTokens(traces)).toBe(7200);
  });

  it("returns null when there is no context step (or no numeric token)", () => {
    expect(latestContextTokens([t("turn", 1), t("commit", 2)])).toBeNull();
    expect(latestContextTokens([t("context", 1, { promptTokens: "nope" })])).toBeNull();
    expect(latestContextTokens([])).toBeNull();
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

// ---- applyActivity ----

describe("applyActivity", () => {
  function traceFrame(step: string, n: number, extra: Partial<TurnTraceFrame> = {}): TurnTraceFrame {
    return { type: "trace", n, step, title: `${step} ${n}`, detail: "", data: {}, ...extra };
  }

  it("trace speaker step → thinking entry with characterId as who", () => {
    const feed = applyActivity(
      [],
      traceFrame("speaker", 1, { data: { characterId: "mei", name: "Mei" } }),
    );
    expect(feed).toHaveLength(1);
    expect(feed[0].kind).toBe("thinking");
    expect(feed[0].who).toBe("mei");
    expect(feed[0].label).toBe("Mei is about to speak");
  });

  it("trace branch step → branch entry", () => {
    const feed = applyActivity([], traceFrame("branch", 5, { detail: "Two paths" }));
    expect(feed).toHaveLength(1);
    expect(feed[0].kind).toBe("branch");
    expect(feed[0].label).toBe("New paths offered");
    expect(feed[0].detail).toBe("Two paths");
  });

  it("trace plan step → plan entry with title as label", () => {
    const feed = applyActivity(
      [],
      traceFrame("plan", 2, { title: "The narrator opens the scene", detail: "opening" }),
    );
    expect(feed).toHaveLength(1);
    expect(feed[0].kind).toBe("plan");
    expect(feed[0].label).toBe("The narrator opens the scene");
  });

  it("keeps trace ids unique when a later turn reuses the same step index n", () => {
    // `n` orders within a turn and resets each turn; the feed is kept across turns, so a
    // plan/speaker step reusing the same n must not collide (would be a duplicate React key).
    let feed: ActivityEntry[] = [];
    feed = applyActivity(feed, traceFrame("plan", 5, { title: "Plan A" }));
    feed = applyActivity(feed, traceFrame("plan", 5, { title: "Plan B" })); // next turn, same n
    feed = applyActivity(
      feed,
      traceFrame("speaker", 6, { data: { characterId: "mei", name: "Mei" } }),
    );
    feed = applyActivity(
      feed,
      traceFrame("speaker", 6, { data: { characterId: "mei", name: "Mei" } }), // next turn, same n
    );
    const ids = feed.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length); // all ids unique
    expect(ids).toContain("trace-plan-5");
    expect(ids).toContain("trace-plan-5#2");
    expect(ids).toContain("trace-speaker-mei-6");
    expect(ids).toContain("trace-speaker-mei-6#2");
  });

  it("first narration chunk → narration entry; subsequent chunks do NOT duplicate", () => {
    let feed: ActivityEntry[] = [];
    feed = applyActivity(feed, ev("narration", "n1", { text: "Rain ", done: false }));
    feed = applyActivity(feed, ev("narration", "n1", { text: "ticks.", done: true }));
    expect(feed).toHaveLength(1);
    expect(feed[0].kind).toBe("narration");
    expect(feed[0].id).toBe("narration-n1");
  });

  it("internal_thought → thinking entry for that character", () => {
    const feed = applyActivity([], ev("internal_thought", "t1", { characterId: "kira", text: "She knows." }));
    expect(feed).toHaveLength(1);
    expect(feed[0].kind).toBe("thinking");
    expect(feed[0].who).toBe("kira");
  });

  it("first character_dialogue chunk → speaking entry; subsequent chunks do NOT duplicate", () => {
    let feed: ActivityEntry[] = [];
    feed = applyActivity(feed, ev("character_dialogue", "d1", { characterId: "mei", text: "He", done: false }));
    feed = applyActivity(feed, ev("character_dialogue", "d1", { characterId: "mei", text: "llo.", done: true }));
    expect(feed).toHaveLength(1);
    expect(feed[0].kind).toBe("speaking");
    expect(feed[0].who).toBe("mei");
    expect(feed[0].id).toBe("dialogue-d1");
  });

  it("character_action → action entry", () => {
    const feed = applyActivity(
      [],
      ev("character_action", "a1", { characterId: "mei", text: "Mei leans back." }),
    );
    expect(feed[0].kind).toBe("action");
    expect(feed[0].who).toBe("mei");
    expect(feed[0].detail).toBe("Mei leans back.");
  });

  it("state_update with stat → stat entry with delta/value and reason", () => {
    const feed = applyActivity(
      [],
      ev("state_update", "s1", {
        patch: {},
        stat: { characterId: "mei", key: "suspicion", delta: 5, value: 67, reason: "pressed" },
      }),
    );
    expect(feed[0].kind).toBe("stat");
    expect(feed[0].who).toBe("mei");
    expect(feed[0].label).toBe("suspicion +5");
    expect(feed[0].detail).toBe("pressed");
  });

  it("state_update without stat → no entry (same reference)", () => {
    const original: ActivityEntry[] = [];
    const result = applyActivity(original, ev("state_update", "s1", { patch: {}, stat: null }));
    expect(result).toBe(original);
  });

  it("character_status_change → presence entry", () => {
    const feed = applyActivity(
      [],
      ev("character_status_change", "cs1", {
        characterId: "kira", status: "left", reason: "She walked out.", auto: true,
      }),
    );
    expect(feed[0].kind).toBe("presence");
    expect(feed[0].who).toBe("kira");
    expect(feed[0].detail).toBe("She walked out.");
  });

  it("entries are newest first (last added is first in list)", () => {
    let feed: ActivityEntry[] = [];
    feed = applyActivity(feed, ev("narration", "n1", { text: "a", done: true }));
    feed = applyActivity(
      feed,
      traceFrame("speaker", 2, { data: { characterId: "mei", name: "Mei" } }),
    );
    expect(feed[0].kind).toBe("thinking"); // newer
    expect(feed[1].kind).toBe("narration"); // older
  });

  it("caps the feed at 12 entries (oldest dropped)", () => {
    let feed: ActivityEntry[] = [];
    for (let i = 0; i < 14; i++) {
      feed = applyActivity(
        feed,
        traceFrame("speaker", i, {
          data: { characterId: `char${i}`, name: `Char${i}` },
        }),
      );
    }
    expect(feed).toHaveLength(12);
  });

  it("returns same reference for irrelevant frames (error / unknown trace step)", () => {
    const original: ActivityEntry[] = [{ id: "x", kind: "narration", label: "test" }];
    expect(applyActivity(original, { type: "error", message: "x" })).toBe(original);
    expect(applyActivity(original, traceFrame("commit", 1))).toBe(original);
    expect(applyActivity(original, traceFrame("lore", 1))).toBe(original);
  });
});

// ---- applyCharacterActivity ----

describe("applyCharacterActivity", () => {
  function traceFrame(step: string, n: number, extra: Partial<TurnTraceFrame> = {}): TurnTraceFrame {
    return { type: "trace", n, step, title: `${step} ${n}`, detail: "", data: {}, ...extra };
  }

  it("trace speaker step sets the character to thinking", () => {
    const map = applyCharacterActivity(
      {},
      traceFrame("speaker", 1, { data: { characterId: "mei", name: "Mei" } }),
    );
    expect(map.mei).toBe("thinking");
  });

  it("internal_thought sets the character to thinking", () => {
    const map = applyCharacterActivity(
      {},
      ev("internal_thought", "t1", { characterId: "kira", text: "Hmm." }),
    );
    expect(map.kira).toBe("thinking");
  });

  it("first character_dialogue chunk sets the character to speaking", () => {
    const map = applyCharacterActivity(
      { mei: "thinking" },
      ev("character_dialogue", "d1", { characterId: "mei", text: "Hello.", done: false }),
    );
    expect(map.mei).toBe("speaking");
  });

  it("character_dialogue with done:true resets the character to idle", () => {
    const map = applyCharacterActivity(
      { mei: "speaking" },
      ev("character_dialogue", "d1", { characterId: "mei", text: "Bye.", done: true }),
    );
    expect(map.mei).toBe("idle");
  });

  it("returns same reference when character already in target state (no re-render)", () => {
    const original: Record<string, CharacterActivity> = { mei: "thinking" };
    // already thinking — speaker trace for same char is a no-op reference-wise
    const result = applyCharacterActivity(
      original,
      traceFrame("speaker", 1, { data: { characterId: "mei", name: "Mei" } }),
    );
    expect(result).toBe(original);
  });

  it("returns same reference for irrelevant frames (error / unknown trace step)", () => {
    const original: Record<string, CharacterActivity> = { mei: "speaking" };
    expect(applyCharacterActivity(original, { type: "error", message: "x" })).toBe(original);
    expect(applyCharacterActivity(original, traceFrame("commit", 1))).toBe(original);
  });

  it("done:true on an already-idle character returns same reference", () => {
    const original: Record<string, CharacterActivity> = { mei: "idle" };
    const result = applyCharacterActivity(
      original,
      ev("character_dialogue", "d1", { characterId: "mei", text: "end", done: true }),
    );
    expect(result).toBe(original);
  });
});

// ---- applyTurnStatus ----

describe("applyTurnStatus", () => {
  function traceFrame(step: string, n: number, extra: Partial<TurnTraceFrame> = {}): TurnTraceFrame {
    return { type: "trace", n, step, title: `${step} ${n}`, detail: "", data: {}, ...extra };
  }

  it("trace speaker step → thinking, carrying the id and the name", () => {
    const s = applyTurnStatus(
      IDLE_TURN_STATUS,
      traceFrame("speaker", 1, { data: { characterId: "mei", name: "Mei" } }),
    );
    expect(s).toEqual({ phase: "thinking", characterId: "mei", name: "Mei" });
  });

  it("a speaker trace with no characterId is ignored", () => {
    const s = applyTurnStatus(IDLE_TURN_STATUS, traceFrame("speaker", 1, { data: {} }));
    expect(s).toBe(IDLE_TURN_STATUS);
  });

  it("internal_thought → thinking, keeping the speaker trace's name for that character", () => {
    const start = applyTurnStatus(
      IDLE_TURN_STATUS,
      traceFrame("speaker", 1, { data: { characterId: "mei", name: "Mei" } }),
    );
    const s = applyTurnStatus(start, ev("internal_thought", "t1", { characterId: "mei", text: "Hmm." }));
    expect(s).toEqual({ phase: "thinking", characterId: "mei", name: "Mei" });
  });

  it("does NOT carry a stale name onto a different character", () => {
    const start: TurnStatus = { phase: "thinking", characterId: "mei", name: "Mei" };
    const s = applyTurnStatus(start, ev("internal_thought", "t1", { characterId: "kira", text: "…" }));
    expect(s).toEqual({ phase: "thinking", characterId: "kira", name: undefined });
  });

  it("character_action → acting; character_dialogue → speaking", () => {
    let s = applyTurnStatus(IDLE_TURN_STATUS, ev("character_action", "a1", { characterId: "mei", text: "stands" }));
    expect(s.phase).toBe("acting");
    s = applyTurnStatus(s, ev("character_dialogue", "d1", { characterId: "mei", text: "Hi", done: false }));
    expect(s).toEqual({ phase: "speaking", characterId: "mei", name: undefined });
  });

  it("character_dialogue done:true → idle", () => {
    const start: TurnStatus = { phase: "speaking", characterId: "mei" };
    const s = applyTurnStatus(start, ev("character_dialogue", "d1", { characterId: "mei", text: "Bye", done: true }));
    expect(s).toEqual(IDLE_TURN_STATUS);
  });

  it("narration streams as narrating and clears on done", () => {
    let s = applyTurnStatus(IDLE_TURN_STATUS, ev("narration", "n1", { text: "Rain ", done: false }));
    expect(s).toEqual({ phase: "narrating" });
    s = applyTurnStatus(s, ev("narration", "n1", { text: "Rain ticks.", done: true }));
    expect(s.phase).toBe("idle");
  });

  it("a plan trace with data.end → ending (never matched on the prose title)", () => {
    const s = applyTurnStatus(
      { phase: "speaking", characterId: "mei" },
      traceFrame("plan", 7, { title: "Something else entirely", data: { end: true } }),
    );
    expect(s).toEqual({ phase: "ending" });
  });

  it("an ordinary plan trace leaves the status alone", () => {
    const start: TurnStatus = { phase: "speaking", characterId: "mei" };
    expect(applyTurnStatus(start, traceFrame("plan", 3, { title: "Mei is up next" }))).toBe(start);
  });

  it("ending survives the trailing branch/commit frames of the turn", () => {
    let s: TurnStatus = applyTurnStatus(
      { phase: "speaking", characterId: "mei" },
      traceFrame("plan", 7, { data: { end: true } }),
    );
    s = applyTurnStatus(s, traceFrame("branch", 8));
    s = applyTurnStatus(s, traceFrame("commit", 9));
    s = applyTurnStatus(s, ev("branch_choices", "b1", { choices: [] }));
    expect(s.phase).toBe("ending");
  });

  it("an error frame resets to idle", () => {
    const s = applyTurnStatus({ phase: "speaking", characterId: "mei" }, { type: "error", message: "x" });
    expect(s).toEqual(IDLE_TURN_STATUS);
  });

  it("returns the same reference across repeated delta chunks (no per-token re-render)", () => {
    const first = applyTurnStatus(
      IDLE_TURN_STATUS,
      ev("character_dialogue", "d1", { characterId: "mei", text: "Hel", done: false }),
    );
    const second = applyTurnStatus(
      first,
      ev("character_dialogue", "d1", { characterId: "mei", text: "Hello.", done: false }),
    );
    expect(second).toBe(first);
  });

  it("returns the same reference for frames it does not care about", () => {
    const start: TurnStatus = { phase: "thinking", characterId: "mei", name: "Mei" };
    expect(applyTurnStatus(start, traceFrame("lore", 2))).toBe(start);
    expect(applyTurnStatus(start, ev("state_update", "s1", { patch: {}, stat: null }))).toBe(start);
  });
});
