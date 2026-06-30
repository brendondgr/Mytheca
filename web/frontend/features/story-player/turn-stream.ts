// Pure reducer: fold one turn-stream frame into the transcript message list.
// Delta-streamed prose (narration, character_dialogue) accumulates by event id;
// a character_action immediately followed by that character's dialogue merges into
// one beat (name once, action italic + bubble), matching the seeded look.
// state_update / branch_choices are wired into the side panels in a later phase.

import type { PlayEvent, TurnStreamFrame } from "@/lib/events";
import type { SceneMessage } from "./scene-data";

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

/** Fold one story event into the transcript. Non-visible/unknown frames pass through. */
export function mergeFrame(prev: SceneMessage[], frame: TurnStreamFrame): SceneMessage[] {
  if (frame.type === "error") return prev; // surfaced separately by the hook
  const event = frame as PlayEvent;

  switch (event.type) {
    case "narration":
      return mergeDelta(prev, event.id, { kind: "narrator" }, event.data.text);

    case "character_action":
      return [
        ...prev,
        { kind: "char", id: event.id, who: event.data.characterId, action: event.data.text },
      ];

    case "character_dialogue": {
      // Already accumulating this dialogue? extend it.
      if (prev.some((m) => m.id === event.id)) {
        return mergeDelta(prev, event.id, { kind: "char", who: event.data.characterId }, event.data.text);
      }
      // First chunk: merge into a just-emitted action beat from the same speaker.
      const last = prev[prev.length - 1];
      if (
        last &&
        last.kind === "char" &&
        last.who === event.data.characterId &&
        last.text === undefined
      ) {
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
  if (frame.type === "error") return null;
  return frame.sessionId || null;
}
