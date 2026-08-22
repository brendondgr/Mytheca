/**
 * Whether the scene's single-character keyboard shortcuts are active.
 *
 * **This exists to satisfy WCAG 2.1.4 (Character Key Shortcuts, Level A.)** `/` and `?` are
 * single-character bindings on `document`, and the criterion requires at least one of: a way
 * to turn them off, a way to remap them, or that they are active only while a component has
 * focus. `hooks/use-scene-shortcuts.ts` already stands down inside editable targets, which is
 * necessary but is **none of the three** — a screen-reader user browsing the transcript is
 * not inside a text field, and their assistive technology sends single characters to navigate.
 *
 * The "turn off" mechanism is the one that fits: an Options toggle, persisted here.
 *
 * Same shape and the same SSR guard as `lib/theme.ts` and `lib/font-size.ts`.
 */

export const SHORTCUTS_STORAGE_KEY = "mytheca-scene-shortcuts";

/** On by default: they are a real convenience, and the criterion asks for an escape, not an
 *  opt-in. */
export const DEFAULT_SHORTCUTS_ENABLED = true;

export function readShortcutsEnabled(): boolean {
  if (typeof localStorage === "undefined") return DEFAULT_SHORTCUTS_ENABLED;
  try {
    const raw = localStorage.getItem(SHORTCUTS_STORAGE_KEY);
    if (raw === null) return DEFAULT_SHORTCUTS_ENABLED;
    return raw !== "off";
  } catch {
    return DEFAULT_SHORTCUTS_ENABLED;
  }
}

export function writeShortcutsEnabled(enabled: boolean): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(SHORTCUTS_STORAGE_KEY, enabled ? "on" : "off");
    // So a scene already on screen reacts without a reload — `storage` only fires in OTHER
    // tabs, which is exactly the case this event covers and that one does not.
    window.dispatchEvent(new CustomEvent(SHORTCUTS_EVENT));
  } catch {
    /* storage unavailable — the preference simply does not persist */
  }
}

/** Dispatched on the window when the preference changes in THIS tab. */
export const SHORTCUTS_EVENT = "mytheca-shortcuts-change";
