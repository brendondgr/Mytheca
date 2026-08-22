import { describe, it, expect } from "vitest";
import { resolveLayers, PROMPT_LAYER_LABELS } from "./promptLayers";

const CATALOG = ["narrator.system", "character.output", "planner.system"];

describe("resolveLayers", () => {
  it("is all defaults when nothing is overridden", () => {
    expect(resolveLayers(CATALOG, {})).toEqual({
      "narrator.system": "default",
      "character.output": "default",
      "planner.system": "default",
    });
  });

  it("lets the later layer win", () => {
    const out = resolveLayers(CATALOG, {
      global: { "narrator.system": "g" },
      storyline: { "narrator.system": "s" },
      scenario: { "narrator.system": "sc" },
    });
    expect(out["narrator.system"]).toBe("scenario");
  });

  it("resolves each key independently", () => {
    const out = resolveLayers(CATALOG, {
      global: { "narrator.system": "g", "planner.system": "g" },
      storyline: { "character.output": "s" },
      scenario: { "planner.system": "sc" },
    });
    expect(out).toEqual({
      "narrator.system": "global",
      "character.output": "storyline",
      "planner.system": "scenario",
    });
  });

  it("treats a BLANK value as inherit, not as an override", () => {
    // The rule most likely to be got wrong, and the one that decides whether a cleared
    // field looks like a customisation. Whitespace counts as blank, matching the backend's
    // `str(value).strip()`.
    const out = resolveLayers(CATALOG, {
      global: { "narrator.system": "g" },
      storyline: { "narrator.system": "" },
      scenario: { "narrator.system": "   \n " },
    });
    expect(out["narrator.system"]).toBe("global");
  });

  it("falls all the way back to default when every layer is blank", () => {
    const out = resolveLayers(CATALOG, {
      global: { "narrator.system": "" },
      storyline: { "narrator.system": "  " },
      scenario: { "narrator.system": "" },
    });
    expect(out["narrator.system"]).toBe("default");
  });

  it("ignores a key nobody knows about", () => {
    // A stale stored key must not make the UI claim a customisation the backend will
    // never apply — `resolve_prompts` skips unknown keys the same way.
    const out = resolveLayers(CATALOG, { scenario: { "retired.prompt": "x" } });
    expect(out).not.toHaveProperty("retired.prompt");
    expect(Object.keys(out)).toEqual(CATALOG);
  });

  it("survives a null or absent layer", () => {
    expect(
      resolveLayers(CATALOG, { global: null, storyline: undefined, scenario: { "planner.system": "x" } })[
        "planner.system"
      ],
    ).toBe("scenario");
  });

  it("ignores a non-string value rather than crediting a layer for it", () => {
    const out = resolveLayers(CATALOG, {
      scenario: { "narrator.system": 7 as unknown as string },
    });
    expect(out["narrator.system"]).toBe("default");
  });

  it("names the layers in player words", () => {
    // "global" is an implementation word; the reader is choosing between scopes.
    expect(PROMPT_LAYER_LABELS.global).toBe("Everywhere");
    expect(PROMPT_LAYER_LABELS.storyline).toBe("This world");
    expect(PROMPT_LAYER_LABELS.scenario).toBe("This scene");
  });
});
