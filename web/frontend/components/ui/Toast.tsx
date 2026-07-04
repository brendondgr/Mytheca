"use client";

import { createPortal } from "react-dom";
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
}

/** Errors assert (interrupt); info/success announce politely. */
const VARIANT_ROLE: Record<ToastVariant, "status" | "alert"> = {
  info: "status",
  success: "status",
  error: "alert",
};

/**
 * Top-right, stacking notification list rendered in a portal (outside the themed
 * tree, like Modal). Each toast is its own live region via `role` — errors
 * `alert`, info/success `status` — and carries a keyboard-operable dismiss. The
 * `embMsg` entrance is opt-out under reduced motion (`motion-reduce:animate-none`,
 * matching Modal, since portalled content sits outside the global reduced-motion
 * selector).
 */
export function Toast({
  items,
  onDismiss,
}: {
  items: ToastItem[];
  onDismiss: (id: string) => void;
}) {
  if (typeof document === "undefined" || items.length === 0) return null;

  return createPortal(
    <div className="pointer-events-none fixed right-4 top-4 z-[100] flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2">
      {items.map((t) => (
        <div
          key={t.id}
          role={VARIANT_ROLE[t.variant]}
          className={cn(
            "pointer-events-auto flex items-start gap-3 rounded-[4px] border bg-modal px-4 py-3 shadow-[0_12px_30px_rgba(14,9,4,.45)] animate-[embMsg_.2s_ease] motion-reduce:animate-none",
            t.variant === "error" ? "border-danger/50" : "border-field-bd",
          )}
          style={{
            borderLeftWidth: 3,
            borderLeftColor:
              t.variant === "error"
                ? "var(--danger)"
                : t.variant === "success"
                  ? "var(--success)"
                  : "var(--accent)",
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
              className="flex-none rounded-[3px] border border-field-bd px-2 py-1 font-mono text-[10px] uppercase tracking-[0.08em] text-ink-soft hover:text-ink hover:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              {t.action.label}
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => onDismiss(t.id)}
            aria-label="Dismiss notification"
            className="flex-none rounded text-[16px] leading-none text-ink-soft hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            ×
          </button>
        </div>
      ))}
    </div>,
    document.body,
  );
}
