/**
 * Which one-time hints the player has already dismissed.
 *
 * Stored as a **set of ids**, not a single "seen the tour" boolean, so a fourth mark can ship
 * later without re-showing the first three to everyone who already dealt with them. That is
 * the whole reason this is not a version number.
 *
 * Same persistence shape as `lib/theme.ts` / `lib/font-size.ts`, including the SSR guard.
 */

export type CoachMarkId = "composer" | "pov" | "cast-rail";

/** In the order they are offered. One at a time — never a queue on screen. */
export const COACH_MARK_ORDER: readonly CoachMarkId[] = ["composer", "pov", "cast-rail"];

export const COACH_MARKS: Record<CoachMarkId, string> = {
  composer: "Type what you say — or what you do. Enter sends.",
  pov: "Speak as one of the cast, instead of narrating.",
  // Width-neutral wording on purpose: this hint is anchored to the cast rail on a desktop
  // and to the Cast button above the composer on a phone, and it has to read correctly
  // pointing at either.
  "cast-rail": "The cast is here — open anyone to see who they are, and how they feel about you.",
};

export const COACH_MARK_STORAGE_KEY = "mytheca-coach-marks";

/** The ids already dismissed. `[]` on the server, or when storage is unavailable. */
export function readDismissed(): CoachMarkId[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const raw = localStorage.getItem(COACH_MARK_STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((id): id is CoachMarkId => id in COACH_MARKS);
  } catch {
    // Private browsing, a quota error, or a hand-mangled value. A hint that cannot remember
    // being dismissed is a small annoyance; a crash on load is not.
    return [];
  }
}

/** Record one as dismissed. Best-effort — storage failing must never break the scene. */
export function writeDismissed(ids: CoachMarkId[]): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(COACH_MARK_STORAGE_KEY, JSON.stringify([...new Set(ids)]));
  } catch {
    /* see readDismissed */
  }
}

/** The next mark to offer, given what has been dismissed and what is on screen. */
export function nextMark(
  dismissed: readonly CoachMarkId[],
  available: readonly CoachMarkId[],
): CoachMarkId | null {
  return (
    COACH_MARK_ORDER.find((id) => available.includes(id) && !dismissed.includes(id)) ?? null
  );
}
