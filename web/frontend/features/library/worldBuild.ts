// Build state for the create-time world build — framework-free so the frame folding
// stays testable apart from the dialog that renders it.
//
// The build console (`BuildWorldModal`) is driven entirely by this state: the phase it
// is in, the step it is on, what has landed so far, and what went wrong. The author
// only leaves for the new world when `phase === "done"`.

import type { PopulateEvent, PopulateOptions } from "@/lib/types";

/** An entity the run actually persisted (the `entity` frame, kept for display). */
export interface BuiltEntity {
  id: string;
  kind: "character" | "setting";
  name: string;
  /** The character's role or the setting's type. */
  role: string;
  image: string | null;
}

export type BuildPhase =
  /** Asking the author what to build. */
  | "ask"
  /** Persisting the storyline / stats / corpus. */
  | "creating"
  /** Streaming the population run. */
  | "building"
  /** Everything finished — the run reported `done`. */
  | "done"
  /** The run ended without finishing. The world still exists. */
  | "failed";

export interface BuildState {
  phase: BuildPhase;
  /** What is happening right now, for the live region. */
  step: string;
  /** Position within the current stage (`0/0` when not applicable). */
  index: number;
  total: number;
  entities: BuiltEntity[];
  /** Non-fatal problems — one per item that failed; the run carried on. */
  problems: string[];
  /** The failure that ended the run, when `phase === "failed"`. */
  error: string | null;
}

export function emptyBuild(): BuildState {
  return {
    phase: "ask",
    step: "",
    index: 0,
    total: 0,
    entities: [],
    problems: [],
    error: null,
  };
}

export function countOf(state: BuildState, kind: BuiltEntity["kind"]): number {
  return state.entities.filter((e) => e.kind === kind).length;
}

/** Fold one populate frame into the build state. */
export function foldPopulateFrame(state: BuildState, frame: PopulateEvent): BuildState {
  switch (frame.type) {
    case "status":
      return {
        ...state,
        phase: "building",
        step: frame.message,
        index: frame.index,
        total: frame.total,
      };
    case "entity":
      return {
        ...state,
        entities: [
          ...state.entities,
          {
            id: frame.id,
            kind: frame.stage,
            name: frame.name,
            role: frame.role ?? "",
            image: frame.image,
          },
        ],
      };
    case "error":
      // A fatal frame ends the run; a non-fatal one is a note beside a world that is
      // still being built.
      return frame.fatal
        ? { ...state, phase: "failed", error: frame.message, step: "" }
        : { ...state, problems: [...state.problems, frame.message] };
    case "done":
      return { ...state, phase: "done", step: "", index: 0, total: 0 };
  }
}

/**
 * A run is only a success if the stream said so.
 *
 * This is the fix for the create page redirecting into a half-built world: a stream
 * that ends without a `done` frame — a dropped connection, a reloaded server, a proxy
 * cutting an idle socket — used to look exactly like completion. Anything short of
 * `done` is a failure the author is told about.
 */
export function finishBuild(state: BuildState, thrown?: unknown): BuildState {
  if (state.phase === "done") return state;
  if (state.phase === "failed" && !thrown) return state;
  const message =
    thrown instanceof Error
      ? thrown.message
      : state.entities.length
        ? "The build stopped early — the world was only partly built."
        : "The build stopped before anything was written.";
  return { ...state, phase: "failed", step: "", error: message };
}

/** A one-line summary of what landed, for the finished dialog. */
export function buildSummary(state: BuildState): string {
  const characters = countOf(state, "character");
  const settings = countOf(state, "setting");
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  return `${plural(characters, "character")} · ${plural(settings, "setting")}`;
}

/** Nothing to build → don't open a stream at all. */
export function willBuild(options: PopulateOptions): boolean {
  return options.enabled;
}
