"use client";

import { useSyncExternalStore } from "react";
import {
  applyFontSizeClass,
  DEFAULT_FONT_SIZE,
  readFontSizeFromDocument,
  FONT_SIZE_STORAGE_KEY,
  type FontSize,
} from "@/lib/font-size";

// Font-size preset is a single global concern backed by the <html> class (the
// source of truth, set pre-paint by the no-flash script). Mirrors the theme
// hook pattern: useSyncExternalStore over a pub-sub singleton so any number
// of components can read/write the preset without a context provider.

const listeners = new Set<() => void>();

function subscribe(callback: () => void): () => void {
  listeners.add(callback);
  return () => {
    listeners.delete(callback);
  };
}

function getSnapshot(): FontSize {
  return readFontSizeFromDocument() ?? DEFAULT_FONT_SIZE;
}

function getServerSnapshot(): FontSize {
  return DEFAULT_FONT_SIZE;
}

/** Switch the active font-size preset: update <html>, persist it, notify subscribers. */
export function setFontSize(next: FontSize): void {
  applyFontSizeClass(next);
  try {
    localStorage.setItem(FONT_SIZE_STORAGE_KEY, next);
  } catch {
    // ignore storage failures (private mode, etc.)
  }
  for (const listener of listeners) listener();
}

export function useFontSize(): {
  fontSize: FontSize;
  setFontSize: typeof setFontSize;
} {
  const fontSize = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot,
  );
  return { fontSize, setFontSize };
}
