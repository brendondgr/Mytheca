/**
 * Find a line in a long scene.
 *
 * Client-side on purpose: the whole transcript is already in memory after rehydration, so a
 * server round-trip would be slower *and* would stop working the moment a substrate is
 * unavailable. Pure functions here, so the matching rules are testable without a DOM.
 */

import type { SceneMessage } from "./scene-data";

export interface BeatMatch {
  /** Index into the messages array. */
  index: number;
  /** How many times the query occurs in this beat — for the total count. */
  count: number;
}

/**
 * Normalise for comparison: case-folded and **diacritic-stripped**.
 *
 * The second part matters more than it looks. These are fantasy transcripts full of names
 * like "Maërin" and "Nyssá"; a player typing "maerin" and getting nothing would reasonably
 * conclude the search is broken rather than that they mistyped an accent they cannot easily
 * produce.
 */
export function normalize(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

/** Everything in a beat a player might be searching for. */
function haystack(m: SceneMessage): string {
  return [m.text, m.action, m.thought, m.image?.caption].filter(Boolean).join(" ");
}

/**
 * The beats matching `query`, in transcript order, with a per-beat occurrence count.
 *
 * A blank query matches nothing rather than everything: "no query" and "every beat" are very
 * different answers, and highlighting the entire scene the instant the bar opens is not a
 * useful state to pass through.
 */
export function matchBeats(messages: SceneMessage[], query: string): BeatMatch[] {
  const needle = normalize(query.trim());
  if (!needle) return [];
  const out: BeatMatch[] = [];
  messages.forEach((m, index) => {
    const hay = normalize(haystack(m));
    if (!hay) return;
    let count = 0;
    let at = hay.indexOf(needle);
    while (at !== -1) {
      count += 1;
      at = hay.indexOf(needle, at + needle.length);
    }
    if (count) out.push({ index, count });
  });
  return out;
}

/** Total occurrences across the transcript — what the count reads out. */
export function totalMatches(matches: BeatMatch[]): number {
  return matches.reduce((n, m) => n + m.count, 0);
}

/**
 * Step through matches, wrapping at both ends.
 *
 * Wrapping rather than stopping: a player at the last match who presses next again means
 * "keep looking", and a dead button at the end of a list reads as a bug.
 */
export function stepMatch(current: number, total: number, delta: 1 | -1): number {
  if (total <= 0) return 0;
  return (current + delta + total) % total;
}
