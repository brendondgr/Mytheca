"use client";

import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { DUR_FAST, ENTER_TRANSITION } from "@/lib/motion";
import { useHydrated } from "@/hooks/use-hydrated";
import { cn } from "@/lib/cn";

export type ToastVariant = "info" | "success" | "error";

export interface ToastAction {
  /** Button label, e.g. "Undo". */
  label: string;
  onClick: () => void;
}

export interface ToastItem {
  id: string;
  message: string;
  variant: ToastVariant;
  title?: string;
  /** Optional single action button (e.g. Undo) rendered before the dismiss control. */
  action?: ToastAction;
  /**
   * How long this toast will live, in ms. `0` means it waits for a manual
   * dismiss. Drives the countdown bar, so the user can see how much reading
   * time is left rather than being surprised by the disappearance.
   */
  durationMs?: number;
}

/** Errors assert (interrupt); info/success announce politely. */
const VARIANT_ROLE: Record<ToastVariant, "status" | "alert"> = {
  info: "status",
  success: "status",
  error: "alert",
};

const VARIANT_ACCENT: Record<ToastVariant, string> = {
  info: "var(--accent)",
  success: "var(--color-success)",
  error: "var(--color-danger)",
};

/**
 * Top-right, stacking notification list rendered in a portal (outside the themed
 * tree, like Modal). Each toast is its own live region via `role` — errors
 * `alert`, info/success `status` — and carries a keyboard-operable dismiss.
 *
 * Framer Motion drives entrance, **exit**, and the `layout` reflow when a toast
 * in the middle of the stack is removed, so the ones below slide up rather than
 * jumping. `MotionConfig reducedMotion="user"` (AppShell) drops all of it under
 * `prefers-reduced-motion` — the portal sits outside the global CSS
 * reduced-motion selector, so the Framer-level handling is what covers it.
 *
 * A countdown bar shows the remaining time, and hovering or focusing a toast
 * pauses both the bar and the dismiss timer: an error you lean in to read must
 * not vanish while you are reading it.
 */
export function Toast({
  items,
  onDismiss,
  onPause,
  onResume,
}: {
  items: ToastItem[];
  onDismiss: (id: string) => void;
  /** Hold this toast's auto-dismiss timer (pointer entered, or focus moved in). */
  onPause?: (id: string) => void;
  /** Release the hold and run out the remaining time. */
  onResume?: (id: string) => void;
}) {
  // The container is portalled unconditionally — even with no toasts — so that
  // `AnimatePresence` survives the dismissal of the LAST one and can animate it
  // out. (Returning null on an empty list unmounts the exiting toast instantly,
  // which is what this component used to do.)
  //
  // That makes the hydration gate necessary: a portal renders nothing on the
  // server but inserts its container into `document.body` on the client, so
  // rendering it on the first client pass leaves React reconciling a <body>
  // child that is absent from the server HTML — a hydration mismatch that
  // regenerates the tree. Waiting one render costs nothing here, since there
  // are never toasts at hydration time anyway.
  const hydrated = useHydrated();
  if (!hydrated) return null;

  return createPortal(
    <div className="pointer-events-none fixed right-4 top-4 z-[100] flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2">
      <AnimatePresence initial={false}>
        {items.map((t) => (
          <motion.div
            key={t.id}
            layout
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            // Exits run at roughly 60% of the entrance, per the motion tokens.
            exit={{ opacity: 0, x: 16, transition: { duration: DUR_FAST } }}
            transition={ENTER_TRANSITION}
            role={VARIANT_ROLE[t.variant]}
            onMouseEnter={() => onPause?.(t.id)}
            onMouseLeave={() => onResume?.(t.id)}
            onFocusCapture={() => onPause?.(t.id)}
            onBlurCapture={() => onResume?.(t.id)}
            className={cn(
              "toast-item pointer-events-auto relative flex items-start gap-3 overflow-hidden rounded-[4px] border bg-modal px-4 py-3 shadow-[0_12px_30px_rgba(14,9,4,.45)]",
              t.variant === "error" ? "border-danger/50" : "border-field-bd",
            )}
            style={{
              borderLeftWidth: 3,
              borderLeftColor: VARIANT_ACCENT[t.variant],
            }}
          >
            <div className="min-w-0 flex-1">
              {t.title ? (
                <p className="font-display text-[13px] font-semibold text-ink">
                  {t.title}
                </p>
              ) : null}
              <p className="break-words font-body text-[13px] leading-snug text-ink-soft">
                {t.message}
              </p>
            </div>
            {t.action ? (
              <button
                type="button"
                onClick={() => {
                  t.action?.onClick();
                  onDismiss(t.id);
                }}
                className="press touch-target-overlay flex-none cursor-pointer rounded-[3px] border border-field-bd px-2 py-1 font-mono text-[10px] uppercase tracking-[0.08em] text-ink-soft transition duration-fast ease-soft hover:border-accent hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                {t.action.label}
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => onDismiss(t.id)}
              aria-label="Dismiss notification"
              className="press touch-target-overlay flex-none cursor-pointer rounded text-[16px] leading-none text-ink-soft transition duration-fast ease-soft hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              ×
            </button>

            {/* The countdown. `aria-hidden` because the same information is
             * better served to assistive tech by the pause-on-focus behaviour
             * than by a shrinking bar it would have to poll. */}
            {t.durationMs && t.durationMs > 0 ? (
              <span
                aria-hidden="true"
                className="toast-countdown absolute inset-x-0 bottom-0 h-[2px] origin-left"
                style={{
                  background: VARIANT_ACCENT[t.variant],
                  animationDuration: `${t.durationMs}ms`,
                }}
              />
            ) : null}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>,
    document.body,
  );
}
