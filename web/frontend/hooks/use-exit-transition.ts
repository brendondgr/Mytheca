"use client";

import { useEffect, useState } from "react";
import { prefersReducedMotion } from "@/lib/motion";

export interface ExitTransition {
  /** Whether the element should be in the DOM at all. */
  mounted: boolean;
  /**
   * Whether it is on its way out. Spread onto the element as
   * `data-closing={closing || undefined}` so CSS can transition to the exit
   * state; `|| undefined` keeps the attribute off entirely when false, rather
   * than rendering `data-closing="false"`.
   */
  closing: boolean;
}

/**
 * Keep an element mounted for one beat after it is closed, so its exit has
 * something to animate.
 *
 * React unmounts on the same tick a conditional flips, which is why nothing in
 * this app had an exit animation: by the time the browser could transition, the
 * node was already gone. `@starting-style` solves the *entrance* for free, but
 * the exit needs the node to outlive the state change, and the CSS answer
 * (`transition-behavior: allow-discrete` on `display`) only applies to elements
 * the browser itself removes from the top layer — not to a React conditional.
 *
 * Reduced motion unmounts immediately: there is no exit to watch, so holding
 * the node would only delay the dismissal.
 *
 * @param open      What the caller wants.
 * @param exitMs    How long the exit takes. Match the CSS; default `--dur-fast`.
 */
export function useExitTransition(open: boolean, exitMs = 140): ExitTransition {
  const [closing, setClosing] = useState(false);
  const [prevOpen, setPrevOpen] = useState(open);

  // Adjust during render, not in an effect. `mounted` MUST be true on the same
  // commit that `open` becomes true: callers focus into the element as they
  // open it (a menu moves focus to its first option), and an effect-driven
  // mount would leave them reaching into a DOM node that does not exist yet.
  // The mirror case matters too — deferring `closing` by an effect would
  // unmount the element for one frame and then bring it back.
  if (prevOpen !== open) {
    setPrevOpen(open);
    setClosing(!open && !prefersReducedMotion());
  }

  useEffect(() => {
    if (!closing) return;
    const timer = window.setTimeout(() => setClosing(false), exitMs);
    return () => window.clearTimeout(timer);
  }, [closing, exitMs]);

  return { mounted: open || closing, closing };
}
