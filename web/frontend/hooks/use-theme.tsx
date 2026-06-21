"use client";

import { useSyncExternalStore } from "react";
import {
  applyThemeClass,
  DEFAULT_THEME,
  readThemeFromDocument,
  THEME_STORAGE_KEY,
  type Theme,
} from "@/lib/theme";

// Theme is a single global concern backed by the <html> class (the source of
// truth, set pre-paint by the no-flash script). We expose it through
// useSyncExternalStore so reads stay correct across SSR/hydration without a
// setState-in-effect, and any number of components can consume it without a
// context provider.

const listeners = new Set<() => void>();

function subscribe(callback: () => void): () => void {
  listeners.add(callback);
  return () => {
    listeners.delete(callback);
  };
}

function getSnapshot(): Theme {
  return readThemeFromDocument() ?? DEFAULT_THEME;
}

function getServerSnapshot(): Theme {
  return DEFAULT_THEME;
}

/** Switch the active theme: update <html>, persist it, notify subscribers. */
export function setTheme(next: Theme): void {
  applyThemeClass(next);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, next);
  } catch {
    // ignore storage failures (private mode, etc.)
  }
  for (const listener of listeners) listener();
}

export function useTheme(): { theme: Theme; setTheme: typeof setTheme } {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return { theme, setTheme };
}
