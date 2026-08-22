"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";

/** The conversation-record export formats. Moved here from the deleted `ExportMenu`. */
export type ExportFormat = "json" | "md";

/**
 * One row in the scene menu.
 *
 * `render` exists so a row can hold a control that is not a button (a theme switcher, a
 * select) while still reading as a labelled row — the alternative is a second menu for
 * "things that are not buttons", which is how a header ends up with four popovers again.
 * A row with `render` gets a label and the control side by side; every other row is a
 * plain `menuitem` button.
 */
export interface SceneMenuItem {
  key: string;
  label: string;
  /** One short line under the label — what the item does, or why it is disabled. */
  hint?: string;
  icon?: ReactNode;
  onSelect?: () => void;
  disabled?: boolean;
  /**
   * Set for a toggle. The row then renders as a `menuitemcheckbox` with `aria-checked`, so
   * its state is announced rather than inferred — and so the ARIA is actually valid, which
   * `aria-pressed` on a `menuitem` is not.
   */
  pressed?: boolean;
  render?: ReactNode;
}

/**
 * One popover for everything the scene header used to spread across separate controls.
 *
 * **Why one menu.** The header's control cluster is `flex-none` on purpose — letting it
 * shrink pushes its children 50–150 px past the viewport edge rather than 7 px — so every
 * control added to it costs width that a 320 px screen does not have. Collapsing them into
 * a single trigger means the header can *gain* capability while *losing* width.
 *
 * **Built to be extended, not replaced.** `docs/plans/reach.md` Phase 4 adds the remaining
 * header controls, a narrow/wide split and drill-down for panel-owning items. The `items`
 * array and the `extraSlot` foot are the seams it needs, so that phase is an extension
 * rather than a rewrite of this file.
 *
 * Native buttons in a `role="menu"`, Esc and outside-click close, focus moved into the
 * panel on open — the same idiom `SceneConfigMenu` already uses, so there is one popover
 * behaviour in the app rather than two.
 */
export function SceneMenu({
  items,
  extraSlot,
  label = "Scene menu",
  triggerLabel = "Scene",
}: {
  items: SceneMenuItem[];
  extraSlot?: ReactNode;
  label?: string;
  triggerLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative flex-none">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={label}
        className="flex flex-none items-center gap-[6px] rounded-[2px] border border-field-bd px-[9px] py-[6px] font-mono text-[9px] tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent aria-expanded:border-accent aria-expanded:text-accent sm:px-[10px]"
      >
        <span aria-hidden>☰</span>
        <span className="hidden sm:inline">{triggerLabel}</span>
      </button>

      {open ? (
        <div
          ref={panelRef}
          id={panelId}
          role="menu"
          aria-label={label}
          tabIndex={-1}
          className="absolute top-[38px] right-0 z-40 w-[248px] mytheca-menu p-[7px] focus:outline-none"
        >
          {items.map((item) =>
            item.render ? (
              <div
                key={item.key}
                className="flex items-center justify-between gap-[8px] rounded-[3px] px-[11px] py-[9px]"
              >
                <span className="font-display text-[13px] font-semibold text-ink">
                  {item.label}
                </span>
                {item.render}
              </div>
            ) : (
              <button
                key={item.key}
                type="button"
                // A toggle in a menu is a `menuitemcheckbox`, not a `menuitem` wearing
                // `aria-pressed` — that combination is invalid ARIA and screen readers are
                // entitled to ignore the state entirely.
                role={item.pressed === undefined ? "menuitem" : "menuitemcheckbox"}
                disabled={item.disabled}
                aria-checked={item.pressed}
                // The hint is the DESCRIPTION, not part of the name. Left to the default
                // computation it concatenates with the label — "Turn Inspectorwhat the
                // scene read, who it chose, and why" — which is what a screen reader would
                // announce as the item's name.
                aria-label={item.label}
                aria-describedby={item.hint ? `${panelId}-${item.key}-hint` : undefined}
                onClick={() => {
                  item.onSelect?.();
                  // A toggle keeps the panel open: closing it would hide the state change
                  // the player just made. Everything else closes, because it navigated.
                  if (item.pressed === undefined) setOpen(false);
                }}
                className="flex w-full flex-col gap-[2px] rounded-[3px] px-[11px] py-[9px] text-left hover:bg-hover disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-transparent aria-checked:text-accent"
              >
                <span className="flex items-center gap-[7px] font-display text-[13px] font-semibold text-ink">
                  {item.icon ? <span aria-hidden>{item.icon}</span> : null}
                  {item.label}
                </span>
                {item.hint ? (
                  <span
                    id={`${panelId}-${item.key}-hint`}
                    className="font-mono text-tag tracking-[0.04em] text-mute"
                  >
                    {item.hint}
                  </span>
                ) : null}
              </button>
            ),
          )}
          {extraSlot}
        </div>
      ) : null}
    </div>
  );
}
