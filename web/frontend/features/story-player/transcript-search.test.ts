import { describe, expect, it } from "vitest";
import { matchBeats, normalize, stepMatch, totalMatches } from "./transcript-search";
import type { SceneMessage } from "./scene-data";

const beats: SceneMessage[] = [
  { kind: "player", text: "I slide the coin toward Maërin." },
  { kind: "char", who: "mei", text: "She does not touch it.", thought: "A coin means a debt." },
  { kind: "narrator", text: "The lamp gutters. The lamp steadies." },
  { kind: "char", who: "mei", action: "turns away", text: "Nothing." },
];

describe("matchBeats", () => {
  it("finds a beat by its prose", () => {
    expect(matchBeats(beats, "coin").map((m) => m.index)).toEqual([0, 1]);
  });

  it("searches thoughts and actions too, not only spoken text", () => {
    // A player looking for "turns away" is looking for something that happened, and where the
    // engine happens to store it is not their problem.
    expect(matchBeats(beats, "turns away").map((m) => m.index)).toEqual([3]);
    expect(matchBeats(beats, "a debt").map((m) => m.index)).toEqual([1]);
  });

  it("ignores case", () => {
    expect(matchBeats(beats, "THE LAMP").map((m) => m.index)).toEqual([2]);
  });

  it("ignores diacritics, in both directions", () => {
    // These transcripts are full of names like "Maërin". A player typing "maerin" and getting
    // nothing would reasonably conclude the search is broken rather than that they mistyped
    // an accent they cannot easily produce.
    expect(matchBeats(beats, "maerin").map((m) => m.index)).toEqual([0]);
    expect(matchBeats(beats, "Maërin").map((m) => m.index)).toEqual([0]);
  });

  it("counts every occurrence within a beat", () => {
    const [hit] = matchBeats(beats, "lamp");
    expect(hit.count).toBe(2);
    expect(totalMatches(matchBeats(beats, "lamp"))).toBe(2);
  });

  it("matches nothing for a blank query rather than everything", () => {
    // "No query" and "every beat" are very different answers, and highlighting the whole
    // scene the instant the bar opens is not a useful state to pass through.
    expect(matchBeats(beats, "")).toEqual([]);
    expect(matchBeats(beats, "   ")).toEqual([]);
  });

  it("returns matches in transcript order", () => {
    const idx = matchBeats(beats, "e").map((m) => m.index);
    expect(idx).toEqual([...idx].sort((a, b) => a - b));
  });

  it("survives a beat with no text at all", () => {
    expect(matchBeats([{ kind: "choices" }], "anything")).toEqual([]);
  });
});

describe("normalize", () => {
  it("folds case and strips marks", () => {
    expect(normalize("Maërin VOSS")).toBe("maerin voss");
  });
});

describe("stepMatch", () => {
  it("wraps at both ends", () => {
    // A player at the last match who presses next again means "keep looking", and a dead
    // button at the end of a list reads as a bug.
    expect(stepMatch(2, 3, 1)).toBe(0);
    expect(stepMatch(0, 3, -1)).toBe(2);
  });

  it("advances normally in the middle", () => {
    expect(stepMatch(0, 3, 1)).toBe(1);
    expect(stepMatch(2, 3, -1)).toBe(1);
  });

  it("is a no-op with no matches", () => {
    expect(stepMatch(0, 0, 1)).toBe(0);
  });
});
