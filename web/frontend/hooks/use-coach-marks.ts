"use client";

import { useCallback, useState } from "react";
import { useHydrated } from "@/hooks/use-hydrated";
import {
  nextMark,
  readDismissed,
  writeDismissed,
  type CoachMarkId,
} from "@/lib/coachMarks";

/**
 * The one hint to show right now, and how to be rid of it.
 *
 * **One at a time, never a tour.** The review explicitly ruled out a modal walkthrough, so
 * there is no overlay, no backdrop, no forced sequence — the scene stays fully usable, and a
 * player who ignores the hints is never blocked by them.
 *
 * Nothing renders before hydration: the dismissal set lives in `localStorage`, which the
 * server cannot see, so rendering a mark on the first pass would be a hydration mismatch.
 *
 * `available` is what is actually on screen — a hint pointing at nothing is worse than no
 * hint. The cast-rail hint used to be withheld below `lg` for exactly that reason; it is now
 * offered at every width, because the cast is reachable at every width.
 */
export function useCoachMarks(available: readonly CoachMarkId[]): {
  mark: CoachMarkId | null;
  dismiss: (id: CoachMarkId) => void;
} {
  const hydrated = useHydrated();
  const [dismissed, setDismissed] = useState<CoachMarkId[]>(readDismissed);

  const dismiss = useCallback((id: CoachMarkId) => {
    setDismissed((prev) => {
      if (prev.includes(id)) return prev;
      const next = [...prev, id];
      writeDismissed(next);
      return next;
    });
  }, []);

  return { mark: hydrated ? nextMark(dismissed, available) : null, dismiss };
}
