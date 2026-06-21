"use client";

import { MotionConfig } from "framer-motion";

/**
 * App-wide Framer Motion config. `reducedMotion="user"` makes every motion
 * component honor `prefers-reduced-motion` (transforms are dropped, opacity
 * kept) without per-component guards.
 */
export function MotionProvider({ children }: { children: React.ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
