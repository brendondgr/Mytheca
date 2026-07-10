// Pure reducer: fold one turn-stream frame into the transcript message list.
// Delta-streamed prose (narration, character_dialogue) accumulates by event id;
// a character_action immediately followed by that character's dialogue merges into
// one beat (name once, action italic + bubble), matching the seeded look.
// state_update / branch_choices are wired into the side panels in a later phase.

import type { GraphRelationship } from "@/lib/api";
import type {
  CharacterStatusChangeEvent,
  PersistedEvent,
  PersistedTrace,
  PlayEvent,
  PresenceStatus,
  StatPatch,
  TurnStreamFrame,
  TurnTraceFrame,
} from "@/lib/events";
import type { Relationship, SceneChoice, SceneMessage, StatChip } from "./scene-data";

/** Map live graph relationships → the rail's `Relationship` rows (color from the cast). */
export function graphRelationshipsToRel(
  rels: GraphRelationship[],
  cast: { name: string; color: string }[],
): Relationship[] {
  const colorByName = new Map(cast.map((c) => [c.name, c.color]));
  return rels.map((r) => ({
    who: r.sourceName,
    color: colorByName.get(r.sourceName) ?? "#8E2B1C",
    text: `${r.type.replace(/_/g, " ")} ${r.targetName}${r.reason ? ` — ${r.reason}` : ""}`,
  }));
}

/** One turn's worth of ordered trace steps (the Inspector groups by turn). */
export interface TraceTurn {
  id: string;
  label: string;
  steps: TurnTraceFrame[];
}

/**
 * Fold one trace frame into the turn-grouped list. A `turn` step opens a new group
 * (its `detail` = the player's message, used as the group label); every other step
 * appends to the current (latest) group. A stray step before any `turn` marker starts
 * its own group so nothing is dropped.
 */
export function foldTrace(prev: TraceTurn[], frame: TurnTraceFrame): TraceTurn[] {
  if (frame.step === "turn" || prev.length === 0) {
    const label = frame.step === "turn" ? frame.detail || frame.title : frame.title;
    return [...prev, { id: `${prev.length}-${frame.n}`, label, steps: [frame] }];
  }
  const next = prev.slice();
  const last = next[next.length - 1];
  next[next.length - 1] = { ...last, steps: [...last.steps, frame] };
  return next;
}

/**
 * The exact context-window usage (input tokens) recorded on a saved session's traces —
 * the last persisted `context` step's `promptTokens`, or `null` when none exists (older
 * sessions, or an endpoint that reports no usage). Traces arrive ordered by turn then step
 * order, so the last match is the most recent. Lets a resumed scene seed the context dial
 * with the real last value instead of falling back to the char/4 estimate.
 */
export function latestContextTokens(traces: PersistedTrace[]): number | null {
  for (let i = traces.length - 1; i >= 0; i--) {
    if (traces[i].step === "context") {
      const pt = (traces[i].data as { promptTokens?: unknown }).promptTokens;
      if (typeof pt === "number") return pt;
    }
  }
  return null;
}

/** Append/extend the message that owns `id`, or push a new one (delta accumulation). */
function mergeDelta(
  prev: SceneMessage[],
  id: string,
  base: Omit<SceneMessage, "text" | "id">,
  chunk: string,
): SceneMessage[] {
  const idx = prev.findIndex((m) => m.id === id);
  if (idx === -1) return [...prev, { ...base, id, text: chunk }];
  const next = prev.slice();
  next[idx] = { ...next[idx], text: (next[idx].text ?? "") + chunk };
  return next;
}

/** A `char` beat for `who` still awaiting its spoken line — the merge target for that
 * speaker's thought → action → dialogue (all fold into one message). */
function isOpenCharBeat(m: SceneMessage | undefined, who: string): m is SceneMessage {
  return Boolean(m && m.kind === "char" && m.who === who && m.text === undefined);
}

/** Fold one story event into the transcript. Non-visible/unknown frames pass through. */
export function mergeFrame(prev: SceneMessage[], frame: TurnStreamFrame): SceneMessage[] {
  if (frame.type === "error") return prev; // surfaced separately by the hook
  if (frame.type === "trace") return prev; // routed to the Inspector, not the transcript
  const event = frame as PlayEvent;

  switch (event.type) {
    case "narration":
      return mergeDelta(prev, event.id, { kind: "narrator" }, event.data.text);

    case "internal_thought": {
      // A character's private thinking — folded into the SAME beat as their speech, so it
      // reads as one message (thought muted, between name + dialogue). The thought is
      // emitted before the speaker's action/dialogue, so it opens the beat.
      const last = prev[prev.length - 1];
      if (isOpenCharBeat(last, event.data.characterId) && last.thought === undefined) {
        const next = prev.slice();
        next[next.length - 1] = { ...last, thought: event.data.text };
        return next;
      }
      return [
        ...prev,
        { kind: "char", id: event.id, who: event.data.characterId, thought: event.data.text },
      ];
    }

    case "character_action": {
      // Merge into the speaker's still-open beat (e.g. one opened by their thought).
      const last = prev[prev.length - 1];
      if (isOpenCharBeat(last, event.data.characterId) && last.action === undefined) {
        const next = prev.slice();
        next[next.length - 1] = { ...last, action: event.data.text };
        return next;
      }
      return [
        ...prev,
        { kind: "char", id: event.id, who: event.data.characterId, action: event.data.text },
      ];
    }

    case "character_dialogue": {
      // Already accumulating this dialogue? extend it.
      if (prev.some((m) => m.id === event.id)) {
        return mergeDelta(prev, event.id, { kind: "char", who: event.data.characterId }, event.data.text);
      }
      // First chunk: merge into the speaker's still-open beat (their thought/action).
      const last = prev[prev.length - 1];
      if (isOpenCharBeat(last, event.data.characterId)) {
        const next = prev.slice();
        next[next.length - 1] = { ...last, id: event.id, text: event.data.text };
        return next;
      }
      return [
        ...prev,
        { kind: "char", id: event.id, who: event.data.characterId, text: event.data.text },
      ];
    }

    // state_update + branch_choices drive panels (wired in the branch/stat phase).
    default:
      return prev;
  }
}

/** Capture the resolved session id from any envelope frame (for turn resume). */
export function sessionIdOf(frame: TurnStreamFrame): string | null {
  if (frame.type === "error" || frame.type === "trace") return null;
  return frame.sessionId || null;
}

/** Upsert a stat chip from a clamped state_update (match by key, else append). */
export function applyStatUpdate(stats: StatChip[], stat: StatPatch): StatChip[] {
  const key = stat.key.toLowerCase();
  const value = stat.value ?? 0;
  const idx = stats.findIndex(
    (c) => c.label.toLowerCase() === key || c.label.toLowerCase().includes(key),
  );
  const cap = stat.key.charAt(0).toUpperCase() + stat.key.slice(1);
  if (idx === -1) return [...stats, { label: cap, value, reason: stat.reason }];
  const next = stats.slice();
  next[idx] = { ...next[idx], value, reason: stat.reason };
  return next;
}

/**
 * Upsert a stat change into per-character stat state, keyed by the event's `characterId`.
 * The character dossier reads its own character's chips from this map so its stat sliders
 * reflect live values (the flat `applyStatUpdate` list drives the Director rail's global
 * Scene-state chips instead). Unknown character → a new bucket.
 */
export function applyStatByChar(
  byChar: Record<string, StatChip[]>,
  stat: StatPatch,
): Record<string, StatChip[]> {
  const cid = stat.characterId;
  return { ...byChar, [cid]: applyStatUpdate(byChar[cid] ?? [], stat) };
}

/**
 * Build the per-character baseline stats map from each cast member's persisted starting
 * values (`GET /characters/{id}/stats`), fetched before any turn runs this session. Folds
 * through the same `applyStatByChar` upsert live/resumed deltas use, so a stat that never
 * changes still reads as the character's real starting value instead of the schema default.
 */
export function baselineStatsByChar(
  perCharacter: Record<string, Record<string, number>>,
): Record<string, StatChip[]> {
  let byChar: Record<string, StatChip[]> = {};
  for (const [characterId, values] of Object.entries(perCharacter)) {
    for (const [key, value] of Object.entries(values)) {
      byChar = applyStatByChar(byChar, { characterId, key, value, reason: "" });
    }
  }
  return byChar;
}

/** Current scene presence, keyed by characterId (absent → `present`). */
export type PresenceMap = Record<string, PresenceStatus>;

/** Fold one `character_status_change` into the presence map (latest wins). */
export function applyPresence(
  map: PresenceMap,
  event: CharacterStatusChangeEvent,
): PresenceMap {
  return { ...map, [event.data.characterId]: event.data.status };
}

/** The client state rebuilt from a saved play-through's persisted rows. */
export interface RehydratedScene {
  messages: SceneMessage[];
  stats: StatChip[];
  statsByChar: Record<string, StatChip[]>;
  presenceByChar: PresenceMap;
  traceTurns: TraceTurn[];
}

/**
 * Rebuild the transcript, live stats, and Inspector trace from a saved session's
 * persisted rows by **replaying them through the very reducers the live stream uses** —
 * so a reopened scene reads byte-identically to how it was played. The only extra case is
 * the persisted `user_turn` row (never on the live wire — the client shows the player line
 * optimistically), which becomes a `player` beat here. Stale `branch_choices` are skipped:
 * on resume the player simply takes the next turn. `initialStatsByChar` seeds the
 * per-character map (each cast member's persisted starting stats) so a stat never touched
 * by a persisted event still reads as that real value, not the schema default.
 */
export function rehydrateFromHistory(
  events: PersistedEvent[],
  traces: PersistedTrace[],
  initialStatsByChar: Record<string, StatChip[]> = {},
): RehydratedScene {
  let messages: SceneMessage[] = [];
  let stats: StatChip[] = [];
  let statsByChar: Record<string, StatChip[]> = initialStatsByChar;
  let presenceByChar: PresenceMap = {};

  for (const e of events) {
    if (e.type === "user_turn") {
      messages = [...messages, { kind: "player", text: String(e.data.text ?? "") }];
      continue;
    }
    if (e.type === "state_update") {
      const stat = (e.data as { stat?: StatPatch | null }).stat;
      if (stat) {
        stats = applyStatUpdate(stats, stat);
        statsByChar = applyStatByChar(statsByChar, stat);
      }
      continue;
    }
    if (e.type === "character_status_change") {
      presenceByChar = applyPresence(presenceByChar, e as unknown as CharacterStatusChangeEvent);
      continue;
    }
    if (e.type === "branch_choices") continue; // don't resurrect a past fork as active
    // narration / internal_thought / character_action / character_dialogue fold exactly as live.
    messages = mergeFrame(messages, e as unknown as TurnStreamFrame);
  }

  let traceTurns: TraceTurn[] = [];
  for (const t of traces) {
    traceTurns = foldTrace(traceTurns, { type: "trace", ...t } as TurnTraceFrame);
  }

  return { messages, stats, statsByChar, presenceByChar, traceTurns };
}

/** Map streamed branch options to renderable choices (no dice — D11). */
export function branchOptionsToChoices(
  options: { label: string; outcome: string }[],
): SceneChoice[] {
  return options.map((o, i) => ({
    id: `live${i}`,
    label: o.label,
    outcome: o.outcome,
    player: o.label,
    follow: { who: "", text: "" },
  }));
}

// ---- Live activity feed (Phase 5) ----

/**
 * One entry in the live "scene pulse" activity feed. Newest entries are first;
 * `who` is a `characterId` when attributable (name resolution is left to the UI
 * layer, which has access to the cast). `id` is stable across delta chunks of the
 * same underlying event so React keys do not flip on every stream tick.
 */
export interface ActivityEntry {
  id: string;
  kind: "narration" | "thinking" | "speaking" | "action" | "stat" | "presence" | "plan" | "branch";
  who?: string; // characterId
  label: string;
  detail?: string;
}

const ACTIVITY_MAX = 12;

/**
 * Fold one frame into the activity feed. Returns a **new** array (newest first,
 * capped at `ACTIVITY_MAX`) or the *same reference* when the frame is irrelevant,
 * so callers can skip re-renders cheaply.
 *
 * Delta-streamed events (narration, character_dialogue) produce ONE entry on the
 * first chunk and are never duplicated on subsequent chunks (id-keyed dedup).
 */
export function applyActivity(list: ActivityEntry[], frame: TurnStreamFrame): ActivityEntry[] {
  // ---- trace frames ----
  if (frame.type === "trace") {
    const t = frame;
    if (t.step === "speaker") {
      // "X is about to speak" — fires before any character events.
      const characterId = (t.data.characterId as string | undefined) ?? "";
      const name = (t.data.name as string | undefined) ?? characterId;
      if (!characterId) return list;
      const entry: ActivityEntry = {
        id: `trace-speaker-${characterId}-${t.n}`,
        kind: "thinking",
        who: characterId,
        label: `${name} is about to speak`,
      };
      return [entry, ...list].slice(0, ACTIVITY_MAX);
    }
    if (t.step === "branch") {
      const entry: ActivityEntry = {
        id: `trace-branch-${t.n}`,
        kind: "branch",
        label: "New paths offered",
        detail: t.detail || undefined,
      };
      return [entry, ...list].slice(0, ACTIVITY_MAX);
    }
    if (t.step === "plan") {
      const entry: ActivityEntry = {
        id: `trace-plan-${t.n}`,
        kind: "plan",
        label: t.title,
        detail: t.detail || undefined,
      };
      return [entry, ...list].slice(0, ACTIVITY_MAX);
    }
    return list; // all other trace steps are inspector-only
  }

  if (frame.type === "error") return list;

  // ---- story event frames ----
  const event = frame as import("@/lib/events").PlayEvent;

  if (event.type === "narration") {
    // One entry for the whole narration stream — dedup by id.
    if (list.some((e) => e.id === `narration-${event.id}`)) return list;
    const entry: ActivityEntry = {
      id: `narration-${event.id}`,
      kind: "narration",
      label: "The narrator sets the scene",
    };
    return [entry, ...list].slice(0, ACTIVITY_MAX);
  }

  if (event.type === "internal_thought") {
    const cid = event.data.characterId;
    const entry: ActivityEntry = {
      id: `thought-${event.id}`,
      kind: "thinking",
      who: cid,
      label: `${cid} is thinking`,
    };
    return [entry, ...list].slice(0, ACTIVITY_MAX);
  }

  if (event.type === "character_dialogue") {
    // One entry for the whole dialogue stream — dedup by id.
    if (list.some((e) => e.id === `dialogue-${event.id}`)) return list;
    const cid = event.data.characterId;
    const entry: ActivityEntry = {
      id: `dialogue-${event.id}`,
      kind: "speaking",
      who: cid,
      label: `${cid} speaks`,
    };
    return [entry, ...list].slice(0, ACTIVITY_MAX);
  }

  if (event.type === "character_action") {
    const cid = event.data.characterId;
    const entry: ActivityEntry = {
      id: `action-${event.id}`,
      kind: "action",
      who: cid,
      label: `${cid} acts`,
      detail: event.data.text,
    };
    return [entry, ...list].slice(0, ACTIVITY_MAX);
  }

  if (event.type === "state_update" && event.data.stat) {
    const stat = event.data.stat as import("@/lib/events").StatPatch;
    const delta = stat.delta != null ? stat.delta : null;
    const value = stat.value != null ? stat.value : null;
    const change =
      delta != null
        ? `${delta >= 0 ? "+" : ""}${delta}`
        : value != null
          ? String(value)
          : "";
    const entry: ActivityEntry = {
      id: `stat-${event.id}-${stat.key}`,
      kind: "stat",
      who: stat.characterId,
      label: `${stat.key}${change ? ` ${change}` : ""}`,
      detail: stat.reason || undefined,
    };
    return [entry, ...list].slice(0, ACTIVITY_MAX);
  }

  if (event.type === "character_status_change") {
    const { characterId, status, reason } = event.data;
    const entry: ActivityEntry = {
      id: `presence-${event.id}`,
      kind: "presence",
      who: characterId,
      label: `${characterId} → ${status}`,
      detail: reason || undefined,
    };
    return [entry, ...list].slice(0, ACTIVITY_MAX);
  }

  return list;
}

// ---- Per-character activity status (Phase 5) ----

/** Live status of a single character in the current turn. */
export type CharacterActivity = "idle" | "thinking" | "speaking";

/**
 * Fold one frame into the per-character activity map. Returns the **same reference**
 * when nothing changes (avoids unnecessary re-renders). Transitions:
 * - trace `speaker` step or `internal_thought` → "thinking"
 * - first `character_dialogue` chunk → "speaking"
 * - `character_dialogue` with `done: true` → "idle"
 */
export function applyCharacterActivity(
  map: Record<string, CharacterActivity>,
  frame: TurnStreamFrame,
): Record<string, CharacterActivity> {
  if (frame.type === "trace") {
    if (frame.step === "speaker") {
      const cid = frame.data.characterId as string | undefined;
      if (!cid) return map;
      if (map[cid] === "thinking") return map;
      return { ...map, [cid]: "thinking" };
    }
    return map;
  }

  if (frame.type === "error") return map;

  const event = frame as import("@/lib/events").PlayEvent;

  if (event.type === "internal_thought") {
    const cid = event.data.characterId;
    if (map[cid] === "thinking") return map;
    return { ...map, [cid]: "thinking" };
  }

  if (event.type === "character_dialogue") {
    const cid = event.data.characterId;
    if (event.data.done) {
      if (map[cid] === "idle" || map[cid] === undefined) return map;
      return { ...map, [cid]: "idle" };
    }
    if (map[cid] === "speaking") return map;
    return { ...map, [cid]: "speaking" };
  }

  return map;
}
