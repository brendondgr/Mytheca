"use client";

import { MotionConfig } from "framer-motion";
import { useReveal } from "@/hooks/use-reveal";

/**
 * App-wide Framer Motion config. `reducedMotion="user"` makes every motion
 * component honor `prefers-reduced-motion` (transforms are dropped, opacity
 * kept) without per-component guards.
 *
 * It also mounts `useReveal` once for the whole app. The hook is a no-op in
 * Chromium — where `styles/motion.css` drives reveals from `animation-timeline:
 * view()` with no JavaScript at all — and supplies an IntersectionObserver path
 * in the engines that do not ship `view()` yet. Mounting it here rather than
 * per-surface means a component gets the entrance by wearing `.reveal`, with
 * nothing to remember and nothing to wire up.
 */
export function MotionProvider({ children }: { children: React.ReactNode }) {
  useReveal();
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
