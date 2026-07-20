// Mytheca font-size preset model. Four presets ship from day one, each
// expressed as a CSS class (.fs-*) on <html> that overrides the --fs-*
// custom properties defined in styles/themes.css. The active preset is
// persisted to localStorage so it survives reloads — same pattern as
// the theme system in lib/theme.ts.

export type FontSize = "compact" | "default" | "comfortable" | "large";

export const FONT_SIZE_KEYS: readonly FontSize[] = [
  "compact",
  "default",
  "comfortable",
  "large",
];
export const DEFAULT_FONT_SIZE: FontSize = "default";
export const FONT_SIZE_STORAGE_KEY = "mytheca-font-size";

export const FONT_SIZES: {
  key: FontSize;
  label: string;
  description: string;
}[] = [
  { key: "compact", label: "Compact", description: "Dense labels, more on screen" },
  { key: "default", label: "Default", description: "Balanced readability" },
  { key: "comfortable", label: "Comfortable", description: "Relaxed spacing" },
  { key: "large", label: "Large", description: "Maximum legibility" },
];

export function isFontSize(value: unknown): value is FontSize {
  return (
    typeof value === "string" &&
    (FONT_SIZE_KEYS as readonly string[]).includes(value)
  );
}

export function fontSizeClass(fs: FontSize): string {
  return `fs-${fs}`;
}

/** Swap the font-size class on <html>. No-op on the server. */
export function applyFontSizeClass(fs: FontSize): void {
  if (typeof document === "undefined") return;
  const classes = document.documentElement.classList;
  for (const key of FONT_SIZE_KEYS) classes.remove(fontSizeClass(key));
  classes.add(fontSizeClass(fs));
}

/** Read the font-size preset currently expressed by the <html> class, if any. */
export function readFontSizeFromDocument(): FontSize | null {
  if (typeof document === "undefined") return null;
  const classes = document.documentElement.classList;
  return FONT_SIZE_KEYS.find((key) => classes.contains(fontSizeClass(key))) ?? null;
}

/**
 * Inline script (stringified) that runs before paint to apply the saved
 * font-size preset, preventing a flash of the wrong size on load.
 * Injected in app/layout.tsx alongside the theme init script.
 */
export const fontSizeInitScript = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  FONT_SIZE_STORAGE_KEY,
)});var v=${JSON.stringify(
  FONT_SIZE_KEYS,
)};if(t&&v.indexOf(t)>=0){var c=document.documentElement.classList;v.forEach(function(k){c.remove('fs-'+k)});c.add('fs-'+t);}}catch(e){}})();`;
