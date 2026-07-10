// Pure state + reducers for the agentic storyline editor/creator panel.
//
// Framework-free so the conversation folding, scope toggling, and plan→form
// mapping stay unit-testable apart from the React hook (useStorylineAgent).

import type {
  AgentEditFrame,
  AgentMessage,
  StatChange,
  StatDefinition,
  StoryPlan,
  StorylineScope,
} from "@/lib/types";

/** The six scoped storyline fields — order + labels for the scope selector. */
export const AGENT_FIELDS = [
  { key: "title", label: "Title" },
  { key: "genre", label: "Genre" },
  { key: "tagline", label: "Tagline" },
  { key: "premise", label: "Premise" },
  { key: "worldPrimer", label: "World Primer" },
  { key: "statistics", label: "Statistics" },
] as const;

export const AGENT_FIELD_KEYS: readonly string[] = AGENT_FIELDS.map((f) => f.key);
const TEXT_FIELD_KEYS = ["title", "genre", "tagline", "premise", "worldPrimer"];

/** Default scope: nothing writable (safe), everything readable as context. */
export function defaultScope(writable: readonly string[] = []): StorylineScope {
  const scope: StorylineScope = {};
  for (const f of AGENT_FIELDS) {
    scope[f.key] = { writable: writable.includes(f.key), readable: true };
  }
  return scope;
}

/** Flip a field's writable bit (readable stays as-is; default readable when new). */
export function toggleWritable(scope: StorylineScope, key: string): StorylineScope {
  const cur = scope[key] ?? { writable: false, readable: true };
  return { ...scope, [key]: { ...cur, writable: !cur.writable } };
}

export function writableKeys(scope: StorylineScope): string[] {
  return AGENT_FIELDS.filter((f) => scope[f.key]?.writable).map((f) => f.key);
}

// ---- panel state + frame folding -------------------------------------------

export interface AgentPanelState {
  /** Committed conversation turns (client-session memory sent to the server). */
  messages: AgentMessage[];
  /** The in-progress assistant reply, accumulated from delta frames. */
  streaming: string;
  /** The reviewable plan awaiting approval, if any. */
  pendingPlan: StoryPlan | null;
  /** The content hash the plan was built against (echoed on apply). */
  baseVersion: string | null;
  error: string | null;
}

export function emptyPanel(): AgentPanelState {
  return { messages: [], streaming: "", pendingPlan: null, baseVersion: null, error: null };
}

/** Fold one stream frame into panel state (a `done` message commits the reply). */
export function foldAgentFrame(state: AgentPanelState, frame: AgentEditFrame): AgentPanelState {
  switch (frame.type) {
    case "status":
      return state;
    case "message":
      if (frame.done) {
        const content = state.streaming.trim();
        return {
          ...state,
          streaming: "",
          messages: content ? [...state.messages, { role: "assistant", content }] : state.messages,
        };
      }
      return { ...state, streaming: state.streaming + frame.delta };
    case "plan":
      return { ...state, pendingPlan: frame.plan, baseVersion: frame.baseVersion ?? null };
    case "error":
      return { ...state, error: frame.message };
  }
}

// ---- plan → form patch (create-mode approval + edit-mode local mirror) ------

export interface AppliedFields {
  title?: string;
  genre?: string;
  tagline?: string;
  premise?: string;
  worldPrimer?: string;
  stats?: StatDefinition[];
}

/** Apply a plan's stat changes onto the current stat list (add/update/remove). */
export function applyStatChanges(
  stats: StatDefinition[],
  changes: StatChange[],
): StatDefinition[] {
  let next = [...stats];
  for (const ch of changes) {
    if (ch.changeType === "remove") {
      next = next.filter((s) => s.key !== ch.key);
    } else if (ch.after) {
      const idx = next.findIndex((s) => s.key === ch.key);
      if (idx >= 0) next[idx] = ch.after;
      else next.push(ch.after);
    }
  }
  return next;
}

/** Translate an approved plan into a set of form-field values to apply. */
export function planToFieldPatch(plan: StoryPlan, currentStats: StatDefinition[]): AppliedFields {
  const patch: AppliedFields = {};
  for (const change of plan.changes) {
    if (TEXT_FIELD_KEYS.includes(change.field)) {
      (patch as Record<string, string>)[change.field] = change.after ?? "";
    }
  }
  if (plan.statChanges.length) {
    patch.stats = applyStatChanges(currentStats, plan.statChanges);
  }
  return patch;
}
