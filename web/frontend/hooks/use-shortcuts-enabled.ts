"use client";

import { useCallback, useSyncExternalStore } from "react";
import {
  readShortcutsEnabled,
  SHORTCUTS_EVENT,
  SHORTCUTS_STORAGE_KEY,
  DEFAULT_SHORTCUTS_ENABLED,
} from "@/lib/shortcuts";

/**
 * Whether the scene's single-character shortcuts are switched on (WCAG 2.1.4).
 *
 * `useSyncExternalStore` because the preference genuinely is an external store with two
 * sources — this tab (a `CustomEvent`) and another tab (`storage`) — and expressing it that
 * way avoids a setState-in-effect. The server snapshot is the default, so the first paint
 * behaves as it always has.
 */
export function useShortcutsEnabled(): boolean {
  const subscribe = useCallback((onChange: () => void) => {
    if (typeof window === "undefined") return () => {};
    const onStorage = (e: StorageEvent) => {
      if (e.key === null || e.key === SHORTCUTS_STORAGE_KEY) onChange();
    };
    window.addEventListener(SHORTCUTS_EVENT, onChange);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(SHORTCUTS_EVENT, onChange);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  return useSyncExternalStore(
    subscribe,
    readShortcutsEnabled,
    () => DEFAULT_SHORTCUTS_ENABLED,
  );
}
