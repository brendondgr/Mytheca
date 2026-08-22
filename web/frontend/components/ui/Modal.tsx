"use client";

import { useRef } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";
import { useExitTransition } from "@/hooks/use-exit-transition";
import { useFocusTrap } from "@/hooks/use-focus-trap";
import { useHydrated } from "@/hooks/use-hydrated";

/**
 * How long the panel stays mounted after `open` flips to false, so the exit
 * transition in motion.css has something to animate. Must match `--dur-fast`.
 *
 * This lives in JS rather than riding `display: allow-discrete` because React
 * owns mounting for a portalled div — the browser only runs the discrete-
 * property dance for elements it removes from the top layer itself.
 */
const EXIT_MS = 140;

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
  /**
   * Render a reddish × close button *outside* the panel (hovering at its
   * top-right corner) instead of relying on the caller to place one inside.
   * The panel clips its own content (`overflow-auto`), so an external affordance
   * has to live beside it. The button stays inside the focus trap.
   */
  externalClose?: boolean;
  /**
   * Opt-in: let the panel's columns own their own vertical scroll instead of the
   * whole dialog scrolling. The dialog becomes a non-scrolling `lg:flex` box
   * (capped at `90vh`) so children marked `lg:overflow-y-auto lg:min-h-0` scroll
   * independently; below `lg` it falls back to whole-dialog `overflow-auto`
   * (stacked columns, no nested scroll on phones). Default false → unchanged.
   */
  splitScroll?: boolean;
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
  externalClose = false,
  splitScroll = false,
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  // `open` says what the caller wants; `mounted` says what is on screen. They
  // differ only for the EXIT_MS beat during which the panel is animating out.
  const { mounted, closing } = useExitTransition(open, EXIT_MS);
  const hydrated = useHydrated();

  // Trap/lock/restore lives in `use-focus-trap` so `Drawer` cannot drift from it.
  useFocusTrap({ open, containerRef: panelRef, onClose });

  // Same portal/hydration rule as Toast: a portal inserts into `document.body`
  // on the client but renders nothing on the server. In practice no modal is
  // open at hydration (they open from user action), so this has never fired —
  // but a modal opened straight from initial state would hit exactly the
  // mismatch Toast did, and the failure reads as unrelated when it happens.
  if (!hydrated || !mounted) return null;

  const dialog = (
    <div
      // When an external close is shown, the focus trap lives on the wrapper
      // (so the outside button is reachable); otherwise it lives on the panel.
      ref={externalClose ? undefined : panelRef}
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel}
      aria-labelledby={labelledBy}
      tabIndex={-1}
      onClick={(event) => event.stopPropagation()}
      data-closing={closing || undefined}
      className={cn(
        // dvh, not vh: on mobile the browser chrome makes vh taller than the
        // space actually available, so a 90vh panel can exceed the viewport.
        "modal-panel max-h-[90dvh] w-full max-w-[92vw] rounded-[5px] bg-modal outline-none",
        splitScroll
          ? "overflow-auto lg:flex lg:overflow-hidden"
          : "overflow-auto",
        !externalClose && className,
      )}
      style={{
        border: "1px solid var(--field-bd)",
        boxShadow: "0 24px 60px rgba(14,9,4,.55)",
      }}
    >
      {children}
    </div>
  );

  return createPortal(
    <div
      data-testid="modal-overlay"
      data-closing={closing || undefined}
      // A dialog that is animating away must not accept a click on the way out.
      className={cn(
        "modal-backdrop fixed inset-0 flex items-center justify-center p-4",
        closing && "pointer-events-none",
      )}
      style={{ background: "rgba(14,9,4,.6)", zIndex: z }}
      onClick={onClose}
    >
      {externalClose ? (
        <div
          ref={panelRef}
          onClick={(event) => event.stopPropagation()}
          className={cn("relative max-w-[92vw]", className)}
        >
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="touch-target-overlay press absolute -top-[13px] -right-[13px] z-10 flex h-[33px] w-[33px] cursor-pointer items-center justify-center rounded-full text-[19px] leading-none text-[#F8E9DC] shadow-[0_4px_14px_rgba(14,9,4,.5)] transition duration-fast ease-soft hover:brightness-125 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C24A33] focus-visible:ring-offset-2"
            style={{ background: "#A8321F", border: "1px solid #C24A33" }}
          >
            ×
          </button>
          {dialog}
        </div>
      ) : (
        dialog
      )}
    </div>,
    document.body,
  );
}
