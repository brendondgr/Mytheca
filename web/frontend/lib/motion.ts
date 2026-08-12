/**
 * Motion helpers shared by components that must make a *timing* decision in
 * JavaScript rather than in CSS.
 *
 * Most reduced-motion handling in Mytheca is pure CSS — the app-wide rule in
 * `themes.css` strips `animation` under `.mytheca-themed *`, and components use
 * `motion-reduce:` utilities. This module exists only for the cases where a
 * duration governs *when something unmounts* or *how long a timer runs*, which
 * CSS cannot express.
 */

/**
 * Whether the user has asked for reduced motion.
 *
 * Returns `false` during SSR and in any environment without `matchMedia`
 * (jsdom does not implement it), which is the safe default: it means the code
 * path being guarded is the animated one, and animated code must already be
 * correct — a component that only works under reduced motion would be broken
 * for almost every real user.
 */
/**
 * The motion tokens, restated for Framer Motion.
 *
 * Framer's `transition` prop takes numbers and easing arrays, not CSS custom
 * properties, so it is the one place a duration cannot literally reference
 * `--dur-base`. Declaring them once here keeps the *values* single-sourced even
 * though the mechanism differs: if `--dur-base` changes in themes.css, this is
 * the one other line to change with it.
 *
 * `EASE_OUT` is `--ease-out`'s cubic-bezier control points.
 */
export const EASE_OUT = [0.16, 1, 0.3, 1] as const;

/** `--dur-base` — entrances: transcript beats, scene-pulse rows, toasts. */
export const DUR_BASE = 0.22;

/** `--dur-fast` — exits, always quicker than the entrance they undo. */
export const DUR_FAST = 0.14;

/** The standard entrance for an arriving item. */
export const ENTER_TRANSITION = { duration: DUR_BASE, ease: EASE_OUT } as const;

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
