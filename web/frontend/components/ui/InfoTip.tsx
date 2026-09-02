"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Icon } from "@/components/ui/Icon";
import { cn } from "@/lib/cn";

/**
 * A control's description, available rather than always on screen.
 *
 * **Why it moved.** Every `SceneControlSelect` used to render its help as a paragraph in
 * flow. Measured in the live app, that put 356px of prose into a 996px config panel — 36% of
 * a surface the player has to scroll — to say something each reader needs exactly once. The
 * copy is not the problem; charging every frame for it is.
 *
 * **What does NOT change is the accessibility contract.** The visible bubble is `aria-hidden`
 * and the same text is also rendered `sr-only` under `id`, which the calling control points
 * `aria-describedby` at. A screen reader therefore hears precisely what it heard when this
 * was a paragraph, open or closed, hovered or not — the tip is a *visual* affordance layered
 * on a description that never left.
 *
 * **The 20px button is sized against WCAG 2.5.8, not by eye.** `.touch-target-overlay` projects
 * a 44px hit area on a coarse pointer, but 2.5.8's 24px minimum applies to a mouse too, and
 * the caller sits this button beside a 22px pin. At 20px with the caller's `gap-xs`, the two
 * centres are 27px apart — clear of the 24px-circle spacing exception with room, where an
 * 18px button at `gap-2xs` put them exactly tangent and relied on "tangent is not
 * intersecting" to pass.
 *
 * WCAG 1.4.13 (content on hover or focus), all three parts:
 * - **Hoverable** — the bubble is inside the same element the pointer entered, so moving onto
 *   it does not dismiss it.
 * - **Dismissible** — Escape closes it without moving focus.
 * - **Persistent** — it stays until the pointer leaves, focus leaves, or Escape.
 */
export function InfoTip({
  /** The control this describes, e.g. `"Turn planning"`. Names the button for a reader. */
  label,
  children,
  /** The id the calling control hands to `aria-describedby`. */
  id,
  className,
}: {
  label: string;
  children: ReactNode;
  id?: string;
  className?: string;
}) {
  // Two independent reasons the bubble is showing, because a touch pointer has only one of
  // them. `hover` is set by a MOUSE pointerenter only: a tap fires `pointerenter` immediately
  // before `click`, so a single toggle would open and then close on the same tap, and the
  // control would look broken on exactly the device it was added for.
  const [hover, setHover] = useState(false);
  const [pinned, setPinned] = useState(false);
  const open = hover || pinned;
  const fallbackId = useId();
  const describedId = id ?? fallbackId;
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      // Escape closes the tip and stops there. It must not also close the popover this sits
      // inside — that panel's own Escape handler is on `document` too, so the event is
      // stopped rather than merely handled.
      if (e.key !== "Escape") return;
      e.stopPropagation();
      setHover(false);
      setPinned(false);
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [open]);

  return (
    <span
      ref={ref}
      className={cn("relative flex-none", className)}
      onPointerEnter={(e) => {
        if (e.pointerType === "mouse") setHover(true);
      }}
      onPointerLeave={() => setHover(false)}
    >
      <button
        type="button"
        // Not a toggle in the ARIA sense: `aria-expanded` would promise a disclosure whose
        // content is in the accessibility tree only when open, and this content is always
        // there. The button exists so a touch and a keyboard can reach the same bubble a
        // pointer gets by hovering.
        aria-label={`What ${label} does`}
        aria-describedby={describedId}
        onClick={() => setPinned((p) => !p)}
        onFocus={() => setPinned(true)}
        onBlur={() => setPinned(false)}
        className="touch-target-overlay flex h-[20px] w-[20px] items-center justify-center rounded-full border border-field-bd text-mute hover:border-accent hover:text-accent-ink"
      >
        <Icon name="info" size={12} />
      </button>
      {open ? (
        <span
          aria-hidden
          // Anchored to the right edge and 200px wide: inside a 264px popover whose padding
          // box is 232px, that is the one geometry that cannot clip horizontally. The panel
          // is `overflow-y-auto`, so a bubble wider than the panel would simply be cut off.
          className="absolute top-[calc(100%+4px)] right-0 z-50 w-[200px] rounded-xs border border-cardbd bg-card2 px-xs py-2xs font-body text-eyebrow leading-[1.45] text-ink shadow-md"
        >
          {children}
        </span>
      ) : null}
      <span id={describedId} className="sr-only">
        {children}
      </span>
    </span>
  );
}
