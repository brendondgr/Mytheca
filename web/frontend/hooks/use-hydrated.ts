"use client";

import { useSyncExternalStore } from "react";

/** A store that never changes, so the value is decided purely by which snapshot React asks for. */
const subscribe = () => () => {};
const getClientSnapshot = () => true;
const getServerSnapshot = () => false;

/**
 * `false` during SSR and on the first client render, `true` from the moment
 * hydration is finished.
 *
 * The use case is **portals**. `createPortal` renders nothing on the server —
 * React has no DOM to portal into — but on the client it inserts its container
 * into `document.body` immediately. If a portal renders on the *first* client
 * pass, React finds a child in `<body>` that the server HTML does not contain
 * and reports a hydration mismatch, regenerating the tree.
 *
 * Gating on this makes the first client render agree with the server (nothing),
 * and the portal appears on the render straight after.
 *
 * `useSyncExternalStore` rather than the usual `useState(false)` +
 * `useEffect(() => setMounted(true))`: it expresses "server snapshot vs client
 * snapshot" directly, which is what this actually is, and it avoids a
 * setState-in-effect that React's lint rightly flags as a cascading render.
 * Same idiom the theme store already uses (`hooks/use-theme.tsx`).
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(subscribe, getClientSnapshot, getServerSnapshot);
}
