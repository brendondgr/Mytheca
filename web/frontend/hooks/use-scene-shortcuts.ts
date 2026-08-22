"use client";

import { useEffect } from "react";

/** Is the event coming from somewhere the player is typing? */
function isEditable(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el || !el.tagName) return false;
  const tag = el.tagName.toLowerCase();
  return (
    tag === "input" ||
    tag === "textarea" ||
    tag === "select" ||
    el.isContentEditable === true
  );
}

export interface SceneShortcuts {
  /** Put the caret in the composer. */
  focusComposer: () => void;
  /**
   * Bring the last sent message back for editing. Only fires from an **empty** composer, so
   * it can never destroy something half-written.
   */
  recallLast: () => void;
  /**
   * Close the topmost thing that is open, and report whether anything was closed. Ordered by
   * the caller, because only it knows what is layered.
   */
  closeTopmost: () => boolean;
  /** Toggle the shortcut sheet. */
  toggleHelp: () => void;
}

/**
 * The scene's keyboard bindings, in one document-level listener.
 *
 * **The rule this class of feature always ships without:** every event originating in an
 * editable target is ignored, except the two that genuinely belong there. Typing `/` or `?`
 * into the composer must type `/` or `?` — a shortcut that eats characters out of a text
 * field is worse than no shortcut, and it is the first thing a player will hit.
 *
 * The one real hazard is the composer's `@` mention menu, which already owns
 * Arrow/Enter/Tab/Escape while it is open. This hook stands down inside editable targets
 * entirely, so the menu keeps its keys without either side having to know about the other.
 *
 * Bindings:
 * - `/` — focus the composer (outside a field).
 * - `ArrowUp` — recall the last sent message, from an **empty** composer only.
 * - `Escape` — close the topmost open thing (the caller decides the order).
 * - `?` — the shortcut sheet.
 */
export function useSceneShortcuts(actions: SceneShortcuts, enabled = true): void {
  useEffect(() => {
    if (!enabled) return;

    function onKeyDown(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return; // never shadow a browser shortcut

      const editable = isEditable(e.target);

      // Escape is the one binding that must work from inside a field too — but only once
      // nothing in the composer wants it. The composer handles its own Escape (dismissing
      // the mention menu) and does not let it bubble, so anything arriving here is genuinely
      // spare.
      if (e.key === "Escape") {
        if (actions.closeTopmost()) e.preventDefault();
        return;
      }

      // ArrowUp recalls, and ONLY from an empty composer: recall that overwrites something
      // half-written is a data-loss bug wearing a convenience hat.
      if (e.key === "ArrowUp" && editable) {
        const el = e.target as HTMLTextAreaElement;
        if (el.tagName.toLowerCase() === "textarea" && el.value === "") {
          e.preventDefault();
          actions.recallLast();
        }
        return;
      }

      if (editable) return; // everything below belongs outside a text field

      if (e.key === "/") {
        e.preventDefault();
        actions.focusComposer();
        return;
      }
      if (e.key === "?") {
        e.preventDefault();
        actions.toggleHelp();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [actions, enabled]);
}
