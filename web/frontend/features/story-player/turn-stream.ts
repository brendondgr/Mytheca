// Pure reducer: fold one turn-stream frame into the transcript message list.
// Delta-streamed prose (narration, character_dialogue) accumulates by event id;
// a character_action immediately followed by that character's dialogue merges into
// one beat (name once, action italic + bubble), matching the seeded look.
// state_update / branch_choices are wired into the side panels in a later phase.

import type { GraphRelationship } from "@/lib/api";
import type { PlayEvent, StatPatch, TurnStreamFrame, TurnTraceFrame } from "@/lib/events";
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
