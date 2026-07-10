import { describe, expect, it } from "vitest";
import type { AgentEditFrame, StatDefinition, StoryPlan } from "@/lib/types";
import {
  AGENT_FIELD_KEYS,
  applyStatChanges,
  defaultScope,
  emptyPanel,
  foldAgentFrame,
  planToFieldPatch,
  toggleWritable,
  writableKeys,
} from "./storylineAgent";

const statDef = (key: string, over: Partial<StatDefinition> = {}): StatDefinition => ({
  key,
  displayName: key,
  description: "",
  min: 0,
  max: 100,
  default: 0,
  visibility: "public",
  guidance: null,
  appliesTo: ["character"],
  bands: [],
  ...over,
});

describe("scope", () => {
  it("defaults to nothing writable, everything readable", () => {
    const scope = defaultScope();
    for (const key of AGENT_FIELD_KEYS) {
      expect(scope[key].writable).toBe(false);
      expect(scope[key].readable).toBe(true);
    }
  });

  it("seeds initial writable fields", () => {
    expect(writableKeys(defaultScope(["tagline"]))).toEqual(["tagline"]);
  });

  it("toggleWritable flips one field", () => {
    const scope = toggleWritable(defaultScope(), "premise");
    expect(scope.premise.writable).toBe(true);
    expect(scope.title.writable).toBe(false);
    expect(scope.premise.readable).toBe(true);
  });
});

describe("foldAgentFrame", () => {
  it("accumulates delta then commits on done", () => {
    let s = emptyPanel();
    s = foldAgentFrame(s, { type: "message", delta: "Hel", done: false });
    s = foldAgentFrame(s, { type: "message", delta: "lo", done: false });
    expect(s.streaming).toBe("Hello");
    expect(s.messages).toHaveLength(0);
    s = foldAgentFrame(s, { type: "message", delta: "", done: true });
    expect(s.streaming).toBe("");
    expect(s.messages).toEqual([{ role: "assistant", content: "Hello" }]);
  });

  it("stores a plan and its base version", () => {
    const plan: StoryPlan = { changes: [{ field: "title", after: "X", rationale: "" }], statChanges: [], notes: "" };
    const s = foldAgentFrame(emptyPanel(), { type: "plan", plan, baseVersion: "v1" });
    expect(s.pendingPlan).toBe(plan);
    expect(s.baseVersion).toBe("v1");
  });

  it("records an error", () => {
    const frame: AgentEditFrame = { type: "error", message: "boom" };
    expect(foldAgentFrame(emptyPanel(), frame).error).toBe("boom");
  });
});

describe("applyStatChanges", () => {
  it("adds, updates, and removes by key", () => {
    const start = [statDef("trust", { max: 100 }), statDef("resolve")];
    const next = applyStatChanges(start, [
      { key: "trust", changeType: "update", after: statDef("trust", { max: 80 }), schemaAltering: true, rationale: "" },
      { key: "resolve", changeType: "remove", schemaAltering: true, rationale: "" },
      { key: "grit", changeType: "add", after: statDef("grit"), schemaAltering: true, rationale: "" },
    ]);
    expect(next.map((s) => s.key)).toEqual(["trust", "grit"]);
    expect(next[0].max).toBe(80);
  });
});

describe("planToFieldPatch", () => {
  it("maps text/primer changes and applies stat changes", () => {
    const plan: StoryPlan = {
      changes: [
        { field: "tagline", after: "New tag", rationale: "" },
        { field: "worldPrimer", after: "New primer", rationale: "" },
      ],
      statChanges: [{ key: "grit", changeType: "add", after: statDef("grit"), schemaAltering: true, rationale: "" }],
      notes: "",
    };
    const patch = planToFieldPatch(plan, []);
    expect(patch.tagline).toBe("New tag");
    expect(patch.worldPrimer).toBe("New primer");
    expect(patch.stats?.map((s) => s.key)).toEqual(["grit"]);
    expect(patch.title).toBeUndefined();
  });
});
