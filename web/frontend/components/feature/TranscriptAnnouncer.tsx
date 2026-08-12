"use client";

import { useState } from "react";
import type { SceneMessage } from "@/features/story-player/scene-data";

/** One line of plain prose for a beat, in the order a reader meets it. */
function describe(message: SceneMessage, nameOf: (id?: string) => string): string {
  switch (message.kind) {
    case "narrator":
      return `Narrator. ${message.text ?? ""}`;
    case "choices":
      return "Your move — choose a path.";
    case "player":
      return `You said. ${message.text ?? ""}`;
    case "image":
      return `A picture of the scene. ${message.image?.caption ?? ""}`;
    case "char": {
      const who = nameOf(message.who);
      const parts = [
        message.thought ? `${who} thinks, ${message.thought}` : "",
        message.action ? `${who} ${message.action}` : "",
        message.text ? `${who} said. ${message.text}` : "",
      ].filter(Boolean);
      return parts.join(". ");
    }
    default:
      return message.text ?? "";
  }
}

/**
 * Announces finished beats to assistive tech, once each.
 *
 * The transcript container used to carry `aria-live="polite"` directly. That is
 * wrong for streamed prose: the backend re-emits each event with its **full
 * accumulated text** as it grows, so a live region on the container asks a
 * screen reader to re-read a sentence from the beginning on every delta. The
 * result is unusable — an unbroken stutter for the entire length of a turn.
 *
 * So the announcement is moved off the visual transcript and onto this
 * dedicated region, which speaks once per turn, when the turn is complete. A
 * sighted reader watches the prose arrive; a screen-reader user hears it as
 * finished sentences. Both get the beat, neither gets the stutter.
 *
 * Note the wrapper is `relative`: an `sr-only` element is absolutely
 * positioned, and with no positioned ancestor its containing block is the
 * initial containing block — so it escapes any `overflow: hidden` and grows the
 * ROOT scroller instead. That has bitten this repo before (a doc list added
 * 6212px of blank page below the fold).
 */
export function TranscriptAnnouncer({
  messages,
  streaming,
  nameOf,
}: {
  messages: SceneMessage[];
  /** True while a turn is being written. */
  streaming: boolean;
  /** Resolve a character id to its name, so the announcement is not full of ids. */
  nameOf: (id?: string) => string;
}) {
  const [announcement, setAnnouncement] = useState("");
  const [wasStreaming, setWasStreaming] = useState(streaming);
  // Where this turn's beats begin. Captured when the turn starts, so the
  // announcement covers exactly what the turn added and not the scene so far.
  const [turnStart, setTurnStart] = useState(messages.length);
  // The transcript length as of the PREVIOUS render. `streaming` flipping true
  // and the turn's first beat can land in the same commit, so anchoring on the
  // current length would silently drop that beat from the announcement.
  const [priorLength, setPriorLength] = useState(messages.length);

  if (wasStreaming !== streaming) {
    setWasStreaming(streaming);
    if (streaming) {
      setTurnStart(priorLength);
    } else {
      const added = messages.slice(turnStart);
      setAnnouncement(
        added.length ? added.map((m) => describe(m, nameOf)).join(" ") : "",
      );
    }
  }
  if (priorLength !== messages.length) setPriorLength(messages.length);

  return (
    <p role="status" aria-live="polite" className="sr-only">
      {announcement}
    </p>
  );
}
