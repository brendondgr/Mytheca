"use client";

import { useEffect } from "react";

/**
 * The JavaScript half of the scroll-reveal system.
 *
 * Only engines WITHOUT `animation-timeline: view()` need this — Chromium runs
 * the pure-CSS path in `styles/motion.css` and this hook does nothing there.
 *
 * Everything here is written so that failing produces VISIBLE content, never
 * hidden content, because a permanently-blank section is the worst outcome in
 * the whole motion system:
 *
 *  - `.js-reveal` goes on `<html>` only after the observer is constructed. The
 *    CSS hidden state is scoped under it, so if this module never loads, throws,
 *    or is blocked, no rule matches and everything is simply visible.
 *  - An element is marked `pending` only if it is BELOW the fold at
 *    registration. Anything already on screen — including a deep link landing
 *    mid-page — is marked `shown` immediately and never flashes.
 *  - `unobserve` runs in the callback. Observers stay alive per registered
 *    target, so a 500-item transcript would otherwise recompute geometry every
 *    frame, forever.
 *  - `threshold: 0` with a negative `rootMargin`, never a fractional threshold:
 *    a section taller than the viewport can never reach `intersectionRatio 0.5`
 *    and would stay hidden permanently.
 *  - `pageshow` re-sweeps after a bfcache restore. Registrations survive a back
 *    navigation but produce no new entries, so a restored page would otherwise
 *    show content stuck at `pending`.
 */

const ROOT_CLASS = "js-reveal";
/** px, not %, and not em/rem/vh — those throw SyntaxError in rootMargin. */
const ROOT_MARGIN = "0px 0px -8% 0px";

export function useReveal(enabled = true): void {
  useEffect(() => {
    if (!enabled) return;
    if (typeof window === "undefined") return;

    // Chromium drives this from CSS alone; adding the class there would let two
    // systems animate the same element.
    if (window.CSS?.supports?.("animation-timeline: view()")) return;
    if (typeof IntersectionObserver === "undefined") return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

    const root = document.documentElement;
    const show = (el: Element) => el.setAttribute("data-reveal", "shown");

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          show(entry.target);
          // One-shot: stop paying for geometry on something already revealed.
          observer.unobserve(entry.target);
        }
      },
      { threshold: 0, rootMargin: ROOT_MARGIN },
    );

    // Only now is hiding safe: the observer that will un-hide exists.
    root.classList.add(ROOT_CLASS);

    const register = () => {
      for (const el of document.querySelectorAll<HTMLElement>(".reveal")) {
        if (el.dataset.reveal) continue;
        const box = el.getBoundingClientRect();
        // Already visible (or above the fold) => never hide it, so there is no
        // flash on load and no dependence on the observer firing at all.
        if (box.top < window.innerHeight && box.bottom > 0) {
          show(el);
          continue;
        }
        el.dataset.reveal = "pending";
        observer.observe(el);
      }
    };

    register();

    // The transcript and every column append nodes after mount; a MutationObserver
    // keeps new `.reveal` children in the system without each surface opting in.
    const mutations = new MutationObserver(() => register());
    mutations.observe(document.body, { childList: true, subtree: true });

    // bfcache: registrations survive, entries do not.
    const onPageShow = (event: PageTransitionEvent) => {
      if (!event.persisted) return;
      for (const el of document.querySelectorAll(".reveal[data-reveal='pending']")) {
        show(el);
      }
    };
    window.addEventListener("pageshow", onPageShow);

    return () => {
      window.removeEventListener("pageshow", onPageShow);
      mutations.disconnect();
      observer.disconnect();
      root.classList.remove(ROOT_CLASS);
      // Leaving elements `pending` with the class gone would be harmless (the
      // rule no longer matches) but leaves stale attributes; clear them so a
      // remount starts from a clean sheet.
      for (const el of document.querySelectorAll(".reveal[data-reveal]")) {
        el.removeAttribute("data-reveal");
      }
    };
  }, [enabled]);
}
