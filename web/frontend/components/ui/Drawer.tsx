"use client";

import { useId, useRef } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";
import { CloseButton } from "@/components/ui/CloseButton";
import { useExitTransition } from "@/hooks/use-exit-transition";
import { useFocusTrap } from "@/hooks/use-focus-trap";
import { useHydrated } from "@/hooks/use-hydrated";

/**
 * How long the panel stays mounted after `open` flips to false, so the exit transition in
 * motion.css has something to animate. Must match `--dur-fast`, and matches `Modal`'s for the
 * same reason: React owns mounting for a portalled div, so the browser never runs the
 * discrete-property dance a real `<dialog>` would get.
 */
const EXIT_MS = 140;

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  /**
   * Rendered as a real `<h2>`, not a styled div. A dialog whose name is a paragraph is a
   * dialog a screen-reader user cannot find in a heading list.
   */
  title: string;
  children: React.ReactNode;
  /** How tall the sheet may grow. `dvh`, so mobile browser chrome cannot push it off-screen. */
  heightClass?: string;
  /**
   * Below `Modal`'s 60 on purpose: a modal opened from inside a drawer has to stack above
   * it, not behind it.
   */
  z?: number;
  /** Use instead of `title` when the heading is rendered by the caller. */
  labelledBy?: string;
}

/**
 * A bottom sheet: the mobile counterpart to {@link Modal}, sharing its focus trap, its
 * portal/hydration rule and its exit-transition mechanics.
 *
 * It exists so that a rail can be *the same component* on a phone and on a desktop rather
 * than a second, thinner implementation — which is the only arrangement that guarantees the
 * mobile surface keeps every capability the desktop one gains.
 */
export function Drawer({
  open,
  onClose,
  title,
  children,
  heightClass = "max-h-[80dvh]",
  z = 55,
  labelledBy,
}: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const headingId = useId();
  const { mounted, closing } = useExitTransition(open, EXIT_MS);
  const hydrated = useHydrated();

  useFocusTrap({ open, containerRef: panelRef, onClose });

  // Same portal/hydration rule as Modal and Toast: a portal inserts into `document.body` on
  // the client and renders nothing on the server.
  if (!hydrated || !mounted) return null;

  return createPortal(
    <div
      data-testid="drawer-backdrop"
      data-closing={closing || undefined}
      className={cn(
        "drawer-backdrop fixed inset-0 flex items-end justify-center",
        // A sheet animating away must not accept a click on the way out.
        closing && "pointer-events-none",
      )}
      style={{ background: "rgba(14,9,4,.6)", zIndex: z }}
      onClick={onClose}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy ?? headingId}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        data-closing={closing || undefined}
        className={cn(
          "drawer-panel flex w-full flex-col overflow-hidden rounded-t-[10px] bg-modal outline-none",
          heightClass,
        )}
        style={{
          border: "1px solid var(--field-bd)",
          borderBottom: "none",
          boxShadow: "0 -18px 44px rgba(14,9,4,.5)",
        }}
      >
        {/* Decoration. The sheet is dismissed by the close button, the backdrop or Escape —
            this is the affordance that says "sheet", and announcing it would add a nameless
            control to the trap. */}
        <div aria-hidden className="flex justify-center pt-[8px] pb-[2px]">
          <span className="h-[4px] w-[36px] rounded-full bg-field-bd" />
        </div>
        <div className="flex flex-none items-center justify-between gap-[10px] px-[16px] py-[10px]">
          {labelledBy ? null : (
            <h2
              id={headingId}
              className="min-w-0 truncate font-display text-[16px] font-bold text-ink"
            >
              {title}
            </h2>
          )}
          <CloseButton onClose={onClose} />
        </div>
        {/* The content scrolls, not the sheet: the handle and the close button stay put, so a
            long rail cannot push its own dismiss control off the screen. */}
        <div className="min-h-0 flex-1 overflow-y-auto px-[16px] pb-[16px]">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
