"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Whether a CSS media query currently matches — SSR-safe, and `false` on the server.
 *
 * `useSyncExternalStore` rather than `useState` + `useEffect`: a media query genuinely *is* an
 * external store with a subscription, and expressing it that way avoids both the
 * setState-in-effect the repo's lint rightly flags and the one-frame flash of the wrong
 * answer on mount.
 *
 * The server snapshot is `false` on purpose. Anything gated on this must be safe to be absent
 * on the first paint, which is the correct posture for a progressive enhancement.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (typeof window === "undefined" || !window.matchMedia) return () => {};
      const mql = window.matchMedia(query);
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    },
    [query],
  );

  const getSnapshot = useCallback(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia(query).matches;
  }, [query]);

  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
