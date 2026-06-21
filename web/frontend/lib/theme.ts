// Velora theme model. Three themes ship from day one (docs/design-system.md):
// Parchment (light), Ember (dark), Slate. The active theme is a class on <html>
// and is persisted to localStorage so it survives reloads.

export type Theme = "light" | "dark" | "slate";

export const THEME_KEYS: readonly Theme[] = ["light", "dark", "slate"];
export const DEFAULT_THEME: Theme = "light";
export const THEME_STORAGE_KEY = "velora-theme";

/** Switcher metadata: label + the swatch color shown in the picker dot. */
export const THEMES: { key: Theme; label: string; swatch: string }[] = [
  { key: "light", label: "Parchment", swatch: "#E7DBC2" },
  { key: "dark", label: "Ember", swatch: "#2A2016" },
  { key: "slate", label: "Slate", swatch: "#1A2129" },
];

export function isTheme(value: unknown): value is Theme {
  return typeof value === "string" && (THEME_KEYS as readonly string[]).includes(value);
}

export function themeClass(theme: Theme): string {
  return `theme-${theme}`;
}

/** Swap the theme class on <html>. No-op on the server. */
export function applyThemeClass(theme: Theme): void {
  if (typeof document === "undefined") return;
  const classes = document.documentElement.classList;
  for (const key of THEME_KEYS) classes.remove(themeClass(key));
  classes.add(themeClass(theme));
}

/** Read the theme currently expressed by the <html> class, if any. */
export function readThemeFromDocument(): Theme | null {
  if (typeof document === "undefined") return null;
  const classes = document.documentElement.classList;
  return THEME_KEYS.find((key) => classes.contains(themeClass(key))) ?? null;
}

/**
 * Inline script (stringified) that runs before paint to apply the saved theme,
 * avoiding a flash of the default theme. Injected in app/layout.tsx.
 */
export const themeInitScript = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});var v=${JSON.stringify(
  THEME_KEYS,
)};if(t&&v.indexOf(t)>=0){var c=document.documentElement.classList;v.forEach(function(k){c.remove('theme-'+k)});c.add('theme-'+t);}}catch(e){}})();`;
