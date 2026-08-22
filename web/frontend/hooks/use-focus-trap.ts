"use client";

import { useEffect, useRef, type RefObject } from "react";

/**
 * Every element a keyboard user can land on. Shared so `Modal` and `Drawer` cannot disagree
 * about what "the last focusable thing" is — a trap that cycles to a different last element
 * than the one the user can see is worse than no trap.
 */
export const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * The focus trap shared by every dialog surface: `Modal` and `Drawer` today, whatever comes
 * next tomorrow.
 *
 * Extracted from `Modal` unchanged. It does four things that always travel together and are
 * always got wrong separately — move focus in on open, cycle Tab and Shift+Tab inside the
 * container, lock the body scroll, and put focus back on the trigger when it closes.
 *
 * `onClose` is held in a ref rather than taken as a dependency. That indirection is
 * load-bearing: without it the effect re-runs on every render, and re-running it calls
 * `focus()` again — which yanks the caret out of whatever controlled input the user is typing
 * in. It looks like a stray optimisation and it is a bug fix.
 */
export function useFocusTrap({
  open,
  containerRef,
  onClose,
}: {
  open: boolean;
  /** The element to trap inside. Focus moves to its first focusable child on open. */
  containerRef: RefObject<HTMLElement | null>;
  onClose: () => void;
}) {
  // Keep the latest onClose without making it an effect dependency — see above.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const panel = containerRef.current;
    const previouslyFocused = document.activeElement as HTMLElement | null;

    const focusables = panel?.querySelectorAll<HTMLElement>(FOCUSABLE);
    (focusables && focusables.length > 0 ? focusables[0] : panel)?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        // Stopped, not just handled: a drawer opened from a modal must close only the
        // topmost surface, and both listen on `document`.
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
      // Restored to what it WAS, not to "": a drawer opened over a modal must not unlock the
      // page behind the modal that is still open.
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus?.();
    };
    // `containerRef` is a stable ref object; `onClose` rides the ref above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
}
