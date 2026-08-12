"use client";

import { useEffect, useState } from "react";

/**
 * How long a wait must last before it is worth telling the user about.
 *
 * Below this, an indicator flashes and is gone before it can be read — which
 * reads as *slower* than showing nothing at all, because the eye registers the
 * flicker as a stutter. See docs/frontend-polish-spec.md §3.
 */
export const INDICATOR_DELAY_MS = 300;

/**
 * Gate a loading indicator behind a delay.
 *
 * Returns `false` for the first `delayMs` of an active wait, then `true` until
 * the wait ends. A request that resolves in 150ms therefore shows nothing at
 * all, and the fast path stays visually still.
 *
 * ```tsx
 * const showSpinner = useDelayedFlag(isSaving);
 * ```
 *
 * This is the highest-leverage single change in the loading ladder: it is what
 * separates "the app is working" from "the app is flickering".
 */
export function useDelayedFlag(active: boolean, delayMs = INDICATOR_DELAY_MS): boolean {
  const [show, setShow] = useState(false);
  const [wasActive, setWasActive] = useState(active);

  // Clearing happens during render, not in an effect: the indicator must be
  // gone on the same commit the wait ends, and an effect-driven reset would
  // paint one frame of stale spinner after the data has already arrived.
  if (wasActive !== active) {
    setWasActive(active);
    if (!active) setShow(false);
  }

  useEffect(() => {
    if (!active) return;
    const timer = window.setTimeout(() => setShow(true), delayMs);
    return () => window.clearTimeout(timer);
  }, [active, delayMs]);

  return show;
}
