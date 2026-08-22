import { describe, expect, it } from "vitest";
import {
  availableVerbs,
  BUILT_IN_VERBS,
  MID_SCENE_TURNS,
  VERB_GROUPS,
  type AuthoredVerb,
} from "./sceneVerbs";

const OPEN = { absentCast: [{ id: "kael", name: "Kael" }], settingCount: 3, playerTurns: 9 };
const CLOSED = { absentCast: [], settingCount: 1, playerTurns: 0 };

describe("availableVerbs", () => {
  it("offers every verb when nothing is gated out", () => {
    expect(availableVerbs(OPEN)).toHaveLength(BUILT_IN_VERBS.length);
  });

  it("returns them in group order", () => {
    // The bar draws by group, and a verb arriving out of order would sit under the wrong
    // heading — the grouping is the whole reason this is not a flat row.
    const groups = availableVerbs(OPEN).map((v) => v.group);
    const firstIndex = VERB_GROUPS.map((g) => groups.indexOf(g)).filter((i) => i !== -1);
    expect(firstIndex).toEqual([...firstIndex].sort((a, b) => a - b));
  });

  it("hides `Someone arrives` when there is nobody left in the world", () => {
    // A button that cannot mean anything is exactly what trains a player to stop reading
    // the row.
    expect(availableVerbs(CLOSED).some((v) => v.id === "arrives")).toBe(false);
    expect(availableVerbs(OPEN).some((v) => v.id === "arrives")).toBe(true);
  });

  it("hides `Move the scene` in a storyline with one place", () => {
    expect(availableVerbs({ ...OPEN, settingCount: 1 }).some((v) => v.id === "move")).toBe(false);
    expect(availableVerbs({ ...OPEN, settingCount: 2 }).some((v) => v.id === "move")).toBe(true);
  });

  it("holds the Exit verbs back until the scene has got going", () => {
    const early = availableVerbs({ ...OPEN, playerTurns: MID_SCENE_TURNS - 1 });
    expect(early.some((v) => v.id === "end")).toBe(false);
    expect(early.some((v) => v.id === "wrap")).toBe(false);
    const later = availableVerbs({ ...OPEN, playerTurns: MID_SCENE_TURNS });
    expect(later.some((v) => v.id === "end")).toBe(true);
  });

  it("gives every verb a phrasing distinct from its label", () => {
    // A verb hands the player a sentence to argue with, not a command to fire. A label
    // repeated as its own text would miss the point of the whole surface.
    for (const verb of BUILT_IN_VERBS) {
      if (verb.expands) continue; // an expanding verb inserts nothing itself
      expect(verb.text.length).toBeGreaterThan(verb.label.length);
      expect(verb.text.toLowerCase()).not.toBe(verb.label.toLowerCase());
    }
  });

  it("appends the scene's own verbs after the built-ins of their group", () => {
    const authored: AuthoredVerb[] = [{ label: "Ring the bell", group: "event", text: "The bell rings." }];
    const out = availableVerbs(OPEN, authored);
    const event = out.filter((v) => v.group === "event");
    expect(event[event.length - 1].label).toBe("Ring the bell");
  });

  it("gives an authored verb an id that cannot collide with a built-in", () => {
    const out = availableVerbs(OPEN, [{ label: "escalate", group: "tone", text: "again" }]);
    const ids = out.map((v) => v.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("does not gate an authored verb — the author knows this scene", () => {
    const authored: AuthoredVerb[] = [{ label: "Leave", group: "exit", text: "You go." }];
    expect(availableVerbs(CLOSED, authored).some((v) => v.label === "Leave")).toBe(true);
  });

  it("skips an authored verb missing a label or a phrasing", () => {
    const authored = [
      { label: "  ", group: "event", text: "x" },
      { label: "x", group: "event", text: "  " },
    ] as AuthoredVerb[];
    expect(availableVerbs(CLOSED, authored).filter((v) => v.group === "event")).toHaveLength(
      availableVerbs(CLOSED).filter((v) => v.group === "event").length,
    );
  });
});
