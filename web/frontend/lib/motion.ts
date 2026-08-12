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
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
