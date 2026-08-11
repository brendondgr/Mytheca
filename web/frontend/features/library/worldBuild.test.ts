import { describe, it, expect } from "vitest";
import {
  buildSummary,
  countOf,
  emptyBuild,
  finishBuild,
  foldPopulateFrame,
  willBuild,
  type BuildState,
} from "./worldBuild";
import type { PopulateEvent } from "@/lib/types";

const fold = (frames: PopulateEvent[], from: BuildState = emptyBuild()) =>
  frames.reduce(foldPopulateFrame, from);

const character = (name: string, image: string | null = null): PopulateEvent => ({
  type: "entity",
  stage: "character",
  id: `c-${name}`,
  name,
  role: "Smuggler",
  image,
});

describe("worldBuild.foldPopulateFrame", () => {
  it("tracks the current step and its position", () => {
    const state = fold([
      { type: "status", stage: "roster", message: "Planning…", name: "", index: 0, total: 0 },
      {
        type: "status",
        stage: "character",
        message: "Writing Maerin…",
        name: "Maerin",
        index: 2,
        total: 5,
      },
    ]);
    expect(state.phase).toBe("building");
    expect(state.step).toBe("Writing Maerin…");
    expect([state.index, state.total]).toEqual([2, 5]);
  });

  it("collects each entity that landed, with its role and portrait", () => {
    const state = fold([character("Maerin", "/media/portraits/m.webp")]);
    expect(state.entities).toEqual([
      {
        id: "c-Maerin",
        kind: "character",
        name: "Maerin",
        role: "Smuggler",
        image: "/media/portraits/m.webp",
      },
    ]);
    expect(countOf(state, "character")).toBe(1);
    expect(countOf(state, "setting")).toBe(0);
  });

  it("keeps building through a non-fatal problem", () => {
    const state = fold([
      { type: "error", message: "Could not write Cael.", fatal: false },
      character("Maerin"),
    ]);
    expect(state.problems).toEqual(["Could not write Cael."]);
    expect(state.phase).not.toBe("failed");
    expect(state.entities).toHaveLength(1);
  });

  it("ends on a fatal frame", () => {
    const state = fold([{ type: "error", message: "No model configured.", fatal: true }]);
    expect(state.phase).toBe("failed");
    expect(state.error).toBe("No model configured.");
  });

  it("finishes on done", () => {
    const state = fold([character("Maerin"), { type: "done", characters: 1, settings: 0 }]);
    expect(state.phase).toBe("done");
    expect(state.step).toBe("");
  });
});

// The regression this module exists for: the create page used to redirect into a
// half-built world whenever the stream ended quietly (a dropped connection, a reloaded
// dev server). Silence is not success.
describe("worldBuild.finishBuild", () => {
  it("fails a stream that stopped after writing some of the world", () => {
    const state = finishBuild(fold([character("Maerin")]));
    expect(state.phase).toBe("failed");
    expect(state.error).toMatch(/only partly built/i);
  });

  it("fails a stream that stopped before writing anything", () => {
    const state = finishBuild(fold([]));
    expect(state.phase).toBe("failed");
    expect(state.error).toMatch(/before anything was written/i);
  });

  it("leaves a completed run alone", () => {
    const done = fold([{ type: "done", characters: 0, settings: 0 }]);
    expect(finishBuild(done)).toBe(done);
  });

  it("carries a thrown error through", () => {
    const state = finishBuild(fold([]), new Error("Could not reach the server."));
    expect(state.error).toBe("Could not reach the server.");
  });

  it("prefers a thrown error over an already-fatal frame", () => {
    const fatal = fold([{ type: "error", message: "No model configured.", fatal: true }]);
    expect(finishBuild(fatal).error).toBe("No model configured.");
    expect(finishBuild(fatal, new Error("Aborted.")).error).toBe("Aborted.");
  });
});

describe("worldBuild summaries", () => {
  it("counts what landed, pluralized", () => {
    const state = fold([
      character("Maerin"),
      character("Cael"),
      { type: "entity", stage: "setting", id: "s1", name: "Wharf", role: "Social Hub", image: null },
    ]);
    expect(buildSummary(state)).toBe("2 characters · 1 setting");
    expect(buildSummary(emptyBuild())).toBe("0 characters · 0 settings");
  });

  it("knows when there is nothing to build", () => {
    expect(willBuild({ enabled: true, withArtwork: false })).toBe(true);
    expect(willBuild({ enabled: false, withArtwork: true })).toBe(false);
  });
});
