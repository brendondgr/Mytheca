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

/**
 * Drop any beat still waiting on content.
 *
 * A `speaker` trace opens a beat optimistically, but the engine may then emit nothing for
 * that speaker — a withheld beat, a failed generation, an aborted turn. Called when the
 * stream settles so an empty placeholder never outlives the turn that created it.
 */
export function dropPendingBeats(prev: SceneMessage[]): SceneMessage[] {
  const next = prev.filter(
    (m) =>
      !(
        m.pending &&
        m.text === undefined &&
        m.thought === undefined &&
        m.action === undefined
      ),
  );
  return next.length === prev.length ? prev : next;
}

/** Fold one story event into the transcript. Non-visible/unknown frames pass through. */
export function mergeFrame(prev: SceneMessage[], frame: TurnStreamFrame): SceneMessage[] {
  if (frame.type === "error") return prev; // surfaced separately by the hook
  if (frame.type === "reasoning") return prev; // live-only machinery, folded separately
  if (frame.type === "beat_reroll") {
    // A re-roll is about to stream a new take into an EXISTING beat. Clear it first: the
    // deltas re-emit the same event id, and the accumulator appends by id.
    return clearBeatForReroll(prev, frame.eventId);
  }
  if (frame.type === "trace") {
    // One exception to "traces never touch the transcript": a chosen speaker opens their
    // beat immediately, before a single word exists. The layout commits early, the
    // thought → speech sequence fills one stable place, and the wait stops being a
    // floating pill over an empty transcript.
    if (frame.step !== "speaker") return prev;
    const who = frame.data.characterId as string | undefined;
    if (!who) return prev;
    const last = prev[prev.length - 1];
    if (isOpenCharBeat(last, who)) return prev; // their beat is already open
    return [...prev, { kind: "char", who, pending: true }];
  }
  const event = frame as PlayEvent;

  switch (event.type) {
    case "narration":
      return mergeDelta(prev, event.id, { kind: "narrator" }, event.data.text);

    case "internal_thought": {
      // A character's private thinking — folded into the SAME beat as their speech, so it
      // reads as one message (thought muted, between name + dialogue). The thought is
      // emitted before the speaker's action/dialogue, so it opens the beat.
      //
      // It delta-streams like visible prose, and is usually the FIRST thing a turn can
      // show, so chunks must accumulate rather than replace. Tracked by `thoughtId`
      // because the beat's own `id` belongs to the dialogue that follows.
      const open = prev.findIndex((m) => m.thoughtId === event.id);
      if (open !== -1) {
        const next = prev.slice();
        next[open] = { ...next[open], thought: (next[open].thought ?? "") + event.data.text };
        return next;
      }
      const last = prev[prev.length - 1];
      if (isOpenCharBeat(last, event.data.characterId) && last.thought === undefined) {
        const next = prev.slice();
        next[next.length - 1] = { ...last, thought: event.data.text, thoughtId: event.id };
        return next;
      }
      return [
        ...prev,
        {
          kind: "char",
          id: event.id,
          thoughtId: event.id,
          who: event.data.characterId,
          thought: event.data.text,
        },
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

    case "character_prose":
    case "character_dialogue": {
      // Already accumulating this passage? extend it.
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

    case "scene_image":
      // A picture the player asked for — its own centered beat, appended in stream order
      // so it sits under the moment it depicts (live and on rehydrate alike).
      return [
        ...prev,
        {
          kind: "image",
          id: event.id,
          image: {
            url: event.data.url,
            caption: event.data.caption,
            prompt: event.data.prompt,
          },
        },
      ];

    // state_update + branch_choices drive panels (wired in the branch/stat phase).
    default:
      return prev;
  }
}

/**
 * Fold a live `reasoning` frame into the per-character reasoning map.
 *
 * Keyed by character (the narrator's reasoning lands under `NARRATOR_REASONING`) and
 * cleared when that character's beat opens for real, so the scratchpad is visible during
 * the wait and does not linger under a finished beat. Returns the SAME reference when
 * nothing changes, so a stream of tokens cannot cause needless re-renders elsewhere.
 */
export function applyReasoning(
  prev: Record<string, string>,
  frame: TurnStreamFrame,
): Record<string, string> {
  if (frame.type !== "reasoning") return prev;
  const key = frame.characterId ?? NARRATOR_REASONING;
  if (frame.done) {
    if (!(key in prev)) return prev;
    const next = { ...prev };
    delete next[key];
    return next;
  }
  if (!frame.text) return prev;
  return { ...prev, [key]: (prev[key] ?? "") + frame.text };
}

// ---- Scene direction progress ----

/** One outcome the turn owes the player, and whether it has landed yet. */
export interface DirectionItem {
  text: string;
  delivered: boolean;
  /** Who carried it, once delivered (`null` → the narrator). */
  by?: string | null;
}

/** What the player asked the scene to do this turn, and how far it has got. */
export interface DirectionProgress {
  items: DirectionItem[];
  /** Requirements the scene's beat budget could not fit — reported at the end. */
  undelivered: string[];
}

export const NO_DIRECTION: DirectionProgress = { items: [], undelivered: [] };

/**
 * Fold the `direction` and `plan` trace steps into a live checklist.
 *
 * The engine already broke the player's direction into requirements and already tracked
 * which had landed — but only reported the *result*, at the end, in the Inspector. Folding
 * the per-delivery steps turns that into progress the player can watch: the clearest
 * signal in the app that a long turn is actually going somewhere.
 *
 * Returns the SAME reference when nothing changes (this sees every frame).
 */
export function applyDirection(
  prev: DirectionProgress,
  frame: TurnStreamFrame,
): DirectionProgress {
  if (frame.type !== "trace") return prev;

  if (frame.step === "direction") {
    // The opening step lists everything owed; later steps tick items off.
    const declared = frame.data.requirements as { text?: string }[] | string[] | undefined;
    if (Array.isArray(declared) && declared.length && !("delivered" in frame.data)) {
      const items = declared
        .map((r) => (typeof r === "string" ? r : (r.text ?? "")))
        .filter(Boolean)
        .map((text) => ({ text, delivered: false }));
      return items.length ? { items, undelivered: [] } : prev;
    }
    const delivered = frame.data.delivered as string[] | undefined;
    if (!Array.isArray(delivered) || !delivered.length) return prev;
    const by = (frame.data.characterId as string | null | undefined) ?? null;
    const done = new Set(delivered);
    let changed = false;
    const items = prev.items.map((item) => {
      if (item.delivered || !done.has(item.text)) return item;
      changed = true;
      return { ...item, delivered: true, by };
    });
    // A requirement the engine rebound (or that the client never saw declared) still
    // counts as progress — append it rather than dropping it on the floor.
    const known = new Set(prev.items.map((i) => i.text));
    const extra = delivered.filter((t) => !known.has(t)).map((text) => ({ text, delivered: true, by }));
    if (!changed && !extra.length) return prev;
    return { ...prev, items: [...items, ...extra] };
  }

  if (frame.step === "plan" && Array.isArray(frame.data.undelivered)) {
    const undelivered = (frame.data.undelivered as string[]).filter(Boolean);
    if (!undelivered.length && !prev.undelivered.length) return prev;
    return { ...prev, undelivered };
  }

  return prev;
}

/** Map key for the narrator's own reasoning (it has no character id). */
export const NARRATOR_REASONING = "__narrator__";

/** Capture the resolved session id from any envelope frame (for turn resume). */
export function sessionIdOf(frame: TurnStreamFrame): string | null {
  // Transport frames (error/trace/reasoning/beat_reroll) carry no envelope — only story
  // events do.
  if (
    frame.type === "error" ||
    frame.type === "trace" ||
    frame.type === "reasoning" ||
    frame.type === "beat_reroll"
  ) {
    return null;
  }
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
/**
 * Clear a beat's text before a re-roll's deltas arrive.
 *
 * The deltas re-emit the same event id, and the accumulator appends by id — so without this
 * the new take would be concatenated onto the one it is replacing.
 */
export function clearBeatForReroll(
  messages: SceneMessage[],
  eventId: string,
): SceneMessage[] {
  let changed = false;
  const next = messages.map((m) => {
    if (m.id !== eventId) return m;
    changed = true;
    return { ...m, text: "", action: undefined, thought: undefined };
  });
  return changed ? next : messages;
}

/** Read the take count/active index off an event's data, if it carries them. */
export function takesOf(
  data: Record<string, unknown> | undefined,
): { count: number; active: number } | undefined {
  const takes = data?.takes;
  if (!Array.isArray(takes) || takes.length < 2) return undefined;
  const active = typeof data?.activeTake === "number" ? data.activeTake : 0;
  return { count: takes.length, active };
}

/**
 * Replace one beat's prose by its event id.
 *
 * Lives here, beside `mergeFrame` and `rehydrateFromHistory`, so live, rehydrated and edited
 * transcripts all move through the same module rather than the editor growing its own idea
 * of what a beat is.
 */
export function replaceBeatText(
  messages: SceneMessage[],
  eventId: string,
  text: string,
): SceneMessage[] {
  let changed = false;
  const next = messages.map((m) => {
    if (m.id !== eventId) return m;
    changed = true;
    return { ...m, text };
  });
  // Returning the original array when nothing matched keeps React from re-rendering the
  // whole transcript for an id that is not in it.
  return changed ? next : messages;
}

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
      // Player POV: a user_turn with `data.pov` was authored by the player AS that character
      // → a right-side player-authored character beat. Without `pov` it stays a player beat.
      const pov = e.data.pov;
      // The row id is carried onto the beat so the player's OWN line can be targeted by the
      // beat controls — rewinding and editing your own message is the point of them, and a
      // beat with no id cannot be pointed at. `user_turn` rows never stream, so this is the
      // only place a player beat can acquire one.
      messages =
        typeof pov === "string" && pov
          ? [...messages, { kind: "char", who: pov, fromPlayer: true, text: String(e.data.text ?? ""), id: e.id }]
          : [...messages, { kind: "player", text: String(e.data.text ?? ""), id: e.id }];
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
    // narration / internal_thought / character_action / character_dialogue / scene_image
    // all fold exactly as they do live.
    messages = mergeFrame(messages, e as unknown as TurnStreamFrame);
    // Takes are read on rehydrate rather than threaded through the delta accumulator: they
    // are only ever *complete* when a re-roll finishes, and the re-roll path reloads the
    // session afterwards. Doing it here keeps mergeDelta about accumulating text.
    const takes = takesOf(e.data);
    if (takes) {
      messages = messages.map((m) => (m.id === e.id ? { ...m, takes } : m));
    }
  }

  let traceTurns: TraceTurn[] = [];
  for (const t of traces) {
    traceTurns = foldTrace(traceTurns, { type: "trace", ...t } as TurnTraceFrame);
  }

  return { messages, stats, statsByChar, presenceByChar, traceTurns };
}

/**
 * The current Player POV on resume — the `pov` of the most recent `user_turn` row (or `null`
 * when the last turn was a plain guide/narrator line, or there are no turns yet). Lets a
 * reopened scene restore the "Speaking as" selection so the next line continues in that voice.
 */
export function latestPov(events: PersistedEvent[]): string | null {
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].type !== "user_turn") continue;
    const pov = events[i].data.pov;
    return typeof pov === "string" && pov ? pov : null;
  }
  return null;
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
 * Ensure `base` is unique within `list`. Trace frames number steps with `n`, which
 * *orders within a turn and resets each turn* — so a `plan`/`speaker` step reusing the
 * same `n` in a later turn would otherwise collide with an earlier entry still in the
 * feed window and produce a duplicate React key. On collision, suffix `#2`, `#3`, … so
 * the key stays stable within the window without inventing cross-turn turn numbers the
 * live trace frame doesn't carry.
 */
function uniqueId(base: string, list: ActivityEntry[]): string {
  if (!list.some((e) => e.id === base)) return base;
  let k = 2;
  while (list.some((e) => e.id === `${base}#${k}`)) k += 1;
  return `${base}#${k}`;
}

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
        id: uniqueId(`trace-speaker-${characterId}-${t.n}`, list),
        kind: "thinking",
        who: characterId,
        label: `${name} is about to speak`,
      };
      return [entry, ...list].slice(0, ACTIVITY_MAX);
    }
    if (t.step === "branch") {
      const entry: ActivityEntry = {
        id: uniqueId(`trace-branch-${t.n}`, list),
        kind: "branch",
        label: "New paths offered",
        detail: t.detail || undefined,
      };
      return [entry, ...list].slice(0, ACTIVITY_MAX);
    }
    if (t.step === "plan") {
      const entry: ActivityEntry = {
        id: uniqueId(`trace-plan-${t.n}`, list),
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

  if (event.type === "character_prose" || event.type === "character_dialogue") {
    // One entry for the whole passage — dedup by id.
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

  if (event.type === "character_prose" || event.type === "character_dialogue") {
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

// ---- Whole-scene turn status (who is up, right now) ----

/**
 * What the scene is doing at this instant. Distinct from {@link CharacterActivity}, which is
 * per-character state for the cast rail: this is the SINGLE current focus of the turn, which
 * is what a reader watching the transcript actually needs — who is up, and whether the turn
 * is wrapping up.
 */
export type TurnPhase =
  | "idle"
  // The pre-generation steps. They already streamed as trace frames and were simply
  // ignored here, which is why the strip sat on its generic idle line through the
  // longest, most opaque part of the wait.
  | "gathering"
  | "reading"
  | "planning"
  | "thinking"
  | "speaking"
  | "acting"
  | "narrating"
  | "ending";

/** The scene's current focus. `characterId`/`name` are set only for character phases. */
export interface TurnStatus {
  phase: TurnPhase;
  characterId?: string;
  /** The name carried by the `speaker` trace — the fallback when the cast lookup misses. */
  name?: string;
  /**
   * A short clause explaining the current phase in the turn's own terms — how the player's
   * message was read (`reading`), or why this speaker is up (`thinking`). Rendered under
   * the label; absent when the engine offered no reason.
   */
  detail?: string;
}

/** Nothing is in flight. Also the reset value between turns. */
export const IDLE_TURN_STATUS: TurnStatus = { phase: "idle" };

/** True when both statuses describe the same moment (so the reducer can skip a re-render). */
function sameStatus(a: TurnStatus, b: TurnStatus): boolean {
  return (
    a.phase === b.phase &&
    a.characterId === b.characterId &&
    a.name === b.name &&
    a.detail === b.detail
  );
}

/**
 * Trace steps that name a pre-generation phase.
 *
 * These frames already reached the client (the player sends `trace: true`); the reducer
 * simply dropped them, so the strip showed its generic default for the whole stretch
 * before the first token. Mapping them turns a blank wait into a visible sequence.
 */
const PHASE_BY_STEP: Record<string, TurnPhase> = {
  assemble: "gathering",
  lore: "gathering",
  files: "gathering",
  // `reading`/`planning` are emitted BEFORE their call; `intent`/`direction` after it,
  // carrying the result. Both map to the same phase, so the label stands for the whole
  // window and the detail fills in once the answer is known.
  reading: "reading",
  intent: "reading",
  direction: "reading",
  planning: "planning",
};

/**
 * Fold one frame into the scene's turn status. Returns the **same reference** when nothing
 * changes — this runs on every delta frame, and a fresh object per token would re-render
 * the status strip (and restart its entrance animation) on every chunk of every line.
 *
 * Transitions:
 * - trace `speaker` → `thinking` (a speaker has been chosen; nothing written yet)
 * - trace `plan` with `data.end` → `ending` (the beat loop stopped — see api-contract.md)
 * - `internal_thought` → `thinking` · `character_action` → `acting`
 * - `character_dialogue` → `speaking`, `done: true` → `idle`
 * - `narration` → `narrating`, `done: true` → `idle`
 * - `error` → `idle`; every other frame leaves the status alone
 *
 * Note `ending` is deliberately sticky: the trailing `branch_choices`/`commit`/`reflection`
 * frames are not beats, so they must not knock the "the turn is ending" label back to idle.
 */
export function applyTurnStatus(prev: TurnStatus, frame: TurnStreamFrame): TurnStatus {
  const next = nextTurnStatus(prev, frame);
  return sameStatus(prev, next) ? prev : next;
}

function nextTurnStatus(prev: TurnStatus, frame: TurnStreamFrame): TurnStatus {
  if (frame.type === "trace") {
    if (frame.step === "speaker") {
      const characterId = frame.data.characterId as string | undefined;
      if (!characterId) return prev;
      return {
        phase: "thinking",
        characterId,
        name: (frame.data.name as string | undefined) ?? undefined,
        // The planner's read of the moment — why THIS character is up, and how the beat
        // is pitched. Both are already computed; surfacing them answers the commonest
        // question in play ("why did they answer and not her?").
        detail: speakerReason(frame.data),
      };
    }
    if (frame.step === "plan") {
      if (frame.data.end === true) return { phase: "ending" };
      return { phase: "planning" };
    }
    const phase = PHASE_BY_STEP[frame.step];
    if (phase) {
      return { phase, detail: frame.step === "intent" ? intentReason(frame) : undefined };
    }
    return prev;
  }

  if (frame.type === "error") return IDLE_TURN_STATUS;

  const event = frame as import("@/lib/events").PlayEvent;

  if (event.type === "narration") {
    return event.data.done ? IDLE_TURN_STATUS : { phase: "narrating" };
  }

  if (event.type === "internal_thought") {
    return forCharacter("thinking", event.data.characterId, prev);
  }

  if (event.type === "character_action") {
    return forCharacter("acting", event.data.characterId, prev);
  }

  if (event.type === "character_prose" || event.type === "character_dialogue") {
    if (event.data.done) return IDLE_TURN_STATUS;
    return forCharacter("speaking", event.data.characterId, prev);
  }

  return prev;
}

/**
 * A character phase for `characterId`. The `name` from the `speaker` trace is carried
 * forward **only while it still describes the same character** — story events name a
 * character by id alone, so a stale name from the previous speaker would otherwise be
 * shown against the new one.
 */
/** "she was just accused (tense)" — the planner's reason and register, when given. */
function speakerReason(data: Record<string, unknown>): string | undefined {
  const register = typeof data.register === "string" ? data.register : "";
  const stakes = typeof data.stakes === "string" ? data.stakes.trim() : "";
  if (stakes && register) return `${stakes} (${register})`;
  return stakes || register || undefined;
}

/** "read as: you're telling Beth to confront Mei" — how the message was interpreted. */
function intentReason(frame: { detail?: string; data: Record<string, unknown> }): string | undefined {
  const directive = (frame.detail ?? "").trim();
  if (directive) return directive;
  const kind = typeof frame.data.kind === "string" ? frame.data.kind : "";
  return kind || undefined;
}

function forCharacter(phase: TurnPhase, characterId: string, prev: TurnStatus): TurnStatus {
  return {
    phase,
    characterId,
    name: prev.characterId === characterId ? prev.name : undefined,
  };
}
