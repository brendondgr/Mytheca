"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * A boolean the browser remembers, read without a hydration mismatch.
 *
 * The obvious version — read `localStorage` in an effect and `setState` — renders once with
 * the default, once with the stored value, and trips the "setState synchronously within an
 * effect" rule. The obvious *other* version, reading it in a `useState` initialiser, is worse:
 * the server has no `localStorage`, so the first client paint would disagree with the markup
 * React streamed.
 *
 * `useSyncExternalStore` is the answer, and it is the answer this codebase already uses for
 * the same problem (`use-shortcuts-enabled.ts`). The preference genuinely is an external
 * store with two writers — this tab and another one — and `getServerSnapshot` returning the
 * default is what makes the first paint honest.
 *
 * Written for the direction verb bar's open/closed state. Per browser rather than per scene:
 * a player who wants the verbs wants them everywhere, and one who does not should not have to
 * close them again in every scenario they open.
 */

/** Broadcast within this tab; `storage` covers the others. */
const EVENT = "mytheca:remembered-flag";

function read(key: string, fallback: boolean): boolean {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : raw === "1";
  } catch {
    // Storage blocked (private mode, a locked-down profile). The default is not a failure.
    return fallback;
  }
}

export function useRememberedFlag(
  key: string,
  fallback = false,
): [boolean, (next: boolean) => void] {
  const subscribe = useCallback((onChange: () => void) => {
    if (typeof window === "undefined") return () => {};
    const onStorage = (e: StorageEvent) => {
      if (e.key === null || e.key === key) onChange();
    };
    window.addEventListener(EVENT, onChange);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(EVENT, onChange);
      window.removeEventListener("storage", onStorage);
    };
  }, [key]);

  const value = useSyncExternalStore(
    subscribe,
    () => read(key, fallback),
    () => fallback,
  );

  const set = useCallback(
    (next: boolean) => {
      try {
        window.localStorage.setItem(key, next ? "1" : "0");
      } catch {
        // Nothing to persist to. The dispatch below still updates this tab for this session.
      }
      window.dispatchEvent(new CustomEvent(EVENT));
    },
    [key],
  );

  return [value, set];
}
