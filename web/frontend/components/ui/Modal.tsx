"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  /** Panel sizing/classes (e.g. width). */
  className?: string;
  ariaLabel?: string;
  labelledBy?: string;
  /** Overlay z-index — raise for stacked modals (e.g. a profile over an editor). */
  z?: number;
}

/**
 * Accessible modal: rendered in a portal, focus-trapped, Escape- and
 * backdrop-dismissible, restoring focus to the trigger on close. Entrance uses
 * CSS keyframes (embPop/embDim) with a motion-reduce fallback — deliberately no
 * framer-motion here, so frequent re-renders (controlled inputs) never remount
 * the panel.
 */
export function Modal({
  open,
  onClose,
  children,
  className,
  ariaLabel,
  labelledBy,
  z = 60,
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  // Keep the latest onClose without making it an effect dependency — otherwise
  // the focus-trap effect re-runs every render and steals focus from inputs.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    const previouslyFocused = document.activeElement as HTMLElement | null;

    const focusables = panel?.querySelectorAll<HTMLElement>(FOCUSABLE);
    (focusables && focusables.length > 0 ? focusables[0] : panel)?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const items = panel.querySelectorAll<HTMLElement>(FOCUSABLE);
      if (items.length === 0) {
        event.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus?.();
    };
  }, [open]);

  if (typeof document === "undefined" || !open) return null;

  return createPortal(
    <div
      data-testid="modal-overlay"
      className="fixed inset-0 flex items-center justify-center p-4 animate-[embDim_.15s_ease] motion-reduce:animate-none"
      style={{ background: "rgba(14,9,4,.6)", zIndex: z }}
      onClick={onClose}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel}
        aria-labelledby={labelledBy}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        className={cn(
          "max-h-[90vh] w-full max-w-[92vw] overflow-auto rounded-[5px] bg-modal outline-none animate-[embPop_.2s_ease] motion-reduce:animate-none",
          className,
        )}
        style={{
          border: "1px solid var(--field-bd)",
          boxShadow: "0 24px 60px rgba(14,9,4,.55)",
        }}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
