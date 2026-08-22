"use client";

import { useEffect, useState } from "react";
import { getSettings, type ArtStyleId, type ArtStyleRead } from "@/lib/api";

/**
 * The art-style catalog and the operator's default, for every image picker in the app.
 *
 * Four separate surfaces offer the picker — character portraits, setting art, scenario art,
 * and the in-play scene image — and they are never all mounted at once, so each would
 * otherwise fetch the same settings blob on its own. This caches the answer at module level
 * and shares one in-flight request, so opening the fourth modal costs nothing.
 *
 * The catalog is small, authored, and changes only when the backend does, which is why a
 * process-lifetime cache is the right shape rather than a poll. The one thing that *can*
 * change under it is the operator editing the default in Options — `refresh()` exists for
 * that tab to call after a save, so a picker mounted afterwards pre-selects the new default.
 *
 * Failure is silent and non-blocking: `styles` stays empty and `defaultStyle` stays
 * `"painted"`, which is exactly the look every image had before styles existed. A picker
 * that cannot reach the backend renders nothing rather than blocking the render button.
 */

export const FALLBACK_STYLE: ArtStyleId = "painted";

let cache: { styles: ArtStyleRead[]; defaultStyle: ArtStyleId } | null = null;
let inFlight: Promise<void> | null = null;
const listeners = new Set<() => void>();

async function load(): Promise<void> {
  if (inFlight) return inFlight;
  inFlight = (async () => {
    try {
      const settings = await getSettings();
      cache = {
        styles: settings.comfy.styles ?? [],
        defaultStyle: settings.comfy.artStyle ?? FALLBACK_STYLE,
      };
      listeners.forEach((fn) => fn());
    } catch {
      // Silent: see the docstring. The fallback default is the pre-style behaviour.
    } finally {
      inFlight = null;
    }
  })();
  return inFlight;
}

/** Drop the cache and re-fetch — called by the Options tab after it saves a new default. */
export function refreshArtStyles(): void {
  cache = null;
  void load();
}

/** Test-only: forget everything, so one test's fetch does not satisfy the next one's. */
export function resetArtStylesCache(): void {
  cache = null;
  inFlight = null;
}

export function useArtStyles(): {
  styles: ArtStyleRead[];
  defaultStyle: ArtStyleId;
  loading: boolean;
} {
  const [snapshot, setSnapshot] = useState(cache);

  useEffect(() => {
    const sync = () => setSnapshot(cache);
    listeners.add(sync);
    if (cache) sync();
    else void load();
    return () => {
      listeners.delete(sync);
    };
  }, []);

  return {
    styles: snapshot?.styles ?? [],
    defaultStyle: snapshot?.defaultStyle ?? FALLBACK_STYLE,
    loading: snapshot === null,
  };
}
