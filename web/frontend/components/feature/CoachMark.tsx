"use client";

import { motion } from "framer-motion";

/**
 * One small anchored hint — **not a tour**.
 *
 * No overlay, no backdrop, no forced sequence, no focus trap: the scene stays fully usable
 * behind it and a player who ignores it is never blocked. The review ruled out a modal
 * walkthrough explicitly, and this is what that ruling looks like in a component.
 *
 * Dismissible three ways — the button, `Escape`, or simply acting on the thing it points at
 * (the caller wires that last one, because only it knows what "acting on it" means). Anything
 * that can only be dismissed one way eventually traps someone.
 *
 * Motion honours the repo's global reduced-motion rule: `.mytheca-themed *` already kills
 * every animation under `prefers-reduced-motion`, so a matching base style is all that is
 * needed and no separate media query is written here.
 */
export function CoachMark({
  text,
  onDismiss,
  className,
}: {
  text: string;
  onDismiss: () => void;
  /** Positioning, from the caller — it owns the anchor. */
  className?: string;
}) {
  return (
    <motion.div
      // `status`, not `dialog`: it is an aside about something on screen, and announcing it
      // as a dialog would imply a modality it deliberately does not have.
      role="status"
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onDismiss();
        }
      }}
      className={`z-30 flex max-w-[260px] items-start gap-[8px] rounded-[8px] border border-accent bg-card p-[9px_10px] shadow-lg ${className ?? ""}`}
    >
      <p className="min-w-0 flex-1 font-body text-[12px] leading-[1.45] text-ink-soft">
        {text}
      </p>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Got it"
        // 24x24 minimum target (WCAG 2.5.8) — the glyph is small, the hit area is not.
        className="flex h-[24px] w-[24px] flex-none items-center justify-center rounded-[4px] text-[13px] leading-none text-mute hover:bg-hover hover:text-ink"
      >
        ×
      </button>
    </motion.div>
  );
}
