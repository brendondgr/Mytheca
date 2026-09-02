"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Icon } from "@/components/ui/Icon";

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
  /**
   * A number worth advertising — the present-cast count, the outcomes a direction still
   * owes. `null` or `0` shows nothing. It is folded into the row's accessible name rather
   * than left as a bare numeral, because "Scene 2" tells a screen-reader user nothing.
   *
   * Inherited from the deleted `SceneRailBar`, whose Cast/Scene/Knows triggers moved in
   * here. The badge was the only place those counts existed on a phone.
   */
  count?: number | null;
  /** How the count reads aloud, e.g. `"2 still owed"`. Required whenever `count` shows. */
  countLabel?: (n: number) => string;
  /** Draw attention: the badge fills with accent. For things the scene owes, not totals. */
  urgent?: boolean;
  onSelect?: () => void;
  disabled?: boolean;
  /**
   * Set for a toggle. The row then renders as a `menuitemcheckbox` with `aria-checked`, so
   * its state is announced rather than inferred — and so the ARIA is actually valid, which
   * `aria-pressed` on a `menuitem` is not.
   */
  pressed?: boolean;
  /**
   * Close the menu when this toggle is selected.
   *
   * A toggle normally keeps the menu open, so the player can see the state change they
   * just made. That argument holds for a control whose effect is visible beside the menu
   * — the Turn Inspector docks a rail at `lg` — and fails for one that opens a bottom
   * sheet, because the sheet lands UNDER the panel that is still open in front of it.
   * The rails below `sm` are the second kind.
   */
  closesMenu?: boolean;
  render?: ReactNode;
  /**
   * A panel this row owns. Selecting the row **replaces the menu's rows with this panel**
   * plus a "‹ Back" row, rather than opening a second popover on top of the first.
   *
   * That rule is not a style preference. A popover inside a popover has two Escape targets,
   * two outside-click handlers racing each other and a focus order that leaves the inner
   * panel behind the outer one — it is not operable by keyboard or screen reader in any sane
   * way. Drilling down in place keeps one focus context and one way out.
   */
  panel?: ReactNode;
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
  /** The key of the drilled-into row, or `null` at the top level. */
  const [drilled, setDrilled] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const openItem = drilled ? (items.find((i) => i.key === drilled) ?? null) : null;

  // Reopening at the level the player drilled to last time would be a small mystery every
  // time. Reset on the action that closes, never in an effect watching `open`.
  const close = () => {
    setOpen(false);
    setDrilled(null);
    // Focus goes back to the trigger, synchronously, before the panel unmounts.
    //
    // Standard menu behaviour, and load-bearing since the rails moved in here. A row that
    // opens a bottom sheet is gone the moment it is selected, so `useFocusTrap` — which
    // records `document.activeElement` when the sheet mounts and restores to it on close —
    // would otherwise capture a detached node and drop focus to `<body>`. Escaping out of
    // the sheet would leave a keyboard user at the top of the document.
    triggerRef.current?.focus();
  };

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      // One Escape target, whatever level is showing: Escape steps back out of a panel
      // before it closes the menu, which is what a single focus context implies.
      if (e.key !== "Escape") return;
      if (drilled) setDrilled(null);
      else setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
    // `drilled` is a dependency because Escape's meaning depends on it: step back out of a
    // panel, or close the menu.
  }, [open, drilled]);

  return (
    <div ref={ref} className="relative flex-none">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => (open ? close() : setOpen(true))}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={label}
        // A square below `sm`, matching the back link on the other side of the bar.
        // Sized by `--control` rather than by padding, which is what made the two
        // controls different rectangles wearing the same border.
        className="flex h-control w-control touch-target-overlay flex-none items-center justify-center gap-xs rounded-xs border border-field-bd font-mono text-eyebrow tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent-ink aria-expanded:border-accent aria-expanded:text-accent-ink sm:w-auto sm:px-sm"
      >
        <Icon name="menu" size={16} />
        <span className="hidden sm:inline">{triggerLabel}</span>
      </button>

      {open ? (
        <div
          ref={panelRef}
          id={panelId}
          role="menu"
          aria-label={label}
          tabIndex={-1}
          className="absolute top-2xl right-0 z-40 flex max-h-[calc(100dvh-70px)] w-[248px] flex-col overflow-y-auto mytheca-menu p-xs focus:outline-none"
        >
          {openItem ? (
            <>
              <button
                type="button"
                role="menuitem"
                onClick={() => setDrilled(null)}
                className="flex w-full items-center gap-xs rounded-xs border-b border-hair px-md py-sm text-left font-mono text-eyebrow tracking-[0.12em] text-mute uppercase hover:bg-hover hover:text-ink"
              >
<Icon name="back" size={12} /> Back
              </button>
              <div className="min-h-0 flex-1">{openItem.panel}</div>
            </>
          ) : (
          items.map((item) =>
            item.render ? (
              <div
                key={item.key}
                className="flex items-center justify-between gap-sm rounded-xs px-md py-sm sm:px-sm sm:py-2xs"
              >
                <span className="font-display text-label font-semibold text-ink">
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
                aria-label={
                  item.count && item.countLabel
                    ? `${item.label}, ${item.countLabel(item.count)}`
                    : item.label
                }
                aria-describedby={item.hint ? `${panelId}-${item.key}-hint` : undefined}
                aria-haspopup={item.panel ? "menu" : undefined}
                onClick={() => {
                  if (item.panel) {
                    setDrilled(item.key);
                    return;
                  }
                  item.onSelect?.();
                  // A toggle keeps the panel open: closing it would hide the state change
                  // the player just made. Everything else closes, because it navigated —
                  // as does a toggle that opens a surface this menu would sit on top of.
                  if (item.pressed === undefined || item.closesMenu) close();
                }}
                className="flex w-full flex-col gap-3xs rounded-xs px-md py-sm text-left hover:bg-hover disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-transparent aria-checked:text-accent-ink sm:px-sm sm:py-2xs"
              >
                <span className="flex w-full items-center gap-xs font-display text-label font-semibold text-ink">
                  {item.icon ? <span aria-hidden className="flex-none">{item.icon}</span> : null}
                  <span className="min-w-0 flex-1 truncate">{item.label}</span>
                  {item.count ? (
                    <span
                      aria-hidden
                      className={
                        "flex min-w-[17px] flex-none items-center justify-center rounded-md px-2xs py-3xs font-mono text-eyebrow leading-[1.4] " +
                        (item.urgent
                          ? "bg-accent text-on-accent"
                          : "border border-cardbd bg-card2 text-ink-soft")
                      }
                    >
                      {item.count}
                    </span>
                  ) : null}
                </span>
                {item.hint ? (
                  // One line, `truncate`, with the full text on the native `title`.
                  //
                  // Measured: the hint wrapped to two or three lines in a 248px menu, which
                  // put rows at 71-88px and filled a 720px viewport with six of them. Nothing
                  // is lost to a screen reader — this element is still the row's
                  // `aria-describedby` target and `textContent` is untouched by `truncate` —
                  // and nothing is lost to a pointer, which gets the rest on hover.
                  <span
                    id={`${panelId}-${item.key}-hint`}
                    title={item.hint}
                    className="w-full truncate font-mono text-tag tracking-[0.04em] text-mute"
                  >
                    {item.hint}
                  </span>
                ) : null}
              </button>
            ),
          )
          )}
          {openItem ? null : extraSlot}
        </div>
      ) : null}
    </div>
  );
}
