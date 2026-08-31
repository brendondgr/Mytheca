// Mytheca theme model. Three themes ship from day one (docs/design-system.md):
// Parchment (light), Ember (dark), Slate. The active theme is a class on <html>
// and is persisted to localStorage so it survives reloads.

export type Theme = "light" | "dark" | "slate";

export const THEME_KEYS: readonly Theme[] = ["light", "dark", "slate"];
export const DEFAULT_THEME: Theme = "slate";
export const THEME_STORAGE_KEY = "mytheca-theme";

/** Switcher metadata: label + the swatch color shown in the picker dot. */
export const THEMES: { key: Theme; label: string; swatch: string }[] = [
  { key: "light", label: "Parchment", swatch: "#E7DBC2" },
  { key: "dark", label: "Ember", swatch: "#2A2016" },
  { key: "slate", label: "Slate", swatch: "#1A2129" },
];

/**
 * Each theme's page ground, mirrored from `--page-bg` in styles/themes.css.
 *
 * This is the ONE place a theme colour is duplicated outside the stylesheet,
 * and it is duplicated because `<meta name="theme-color">` cannot read a CSS
 * custom property — the browser paints its own chrome (the mobile address bar,
 * the status bar tint) from this attribute before any stylesheet applies.
 * Without it the chrome stays at the UA default and clashes with whichever
 * theme is active, which is exactly the seam a themed app is judged on when
 * viewed on a phone.
 *
 * `theme-color.test.ts` asserts these stay equal to the stylesheet's values.
 */
export const THEME_PAGE_BG: Record<Theme, string> = {
  light: "#dccca8",
  dark: "#0d0a05",
  slate: "#0a0e13",
};

export function isTheme(value: unknown): value is Theme {
  return typeof value === "string" && (THEME_KEYS as readonly string[]).includes(value);
}

export function themeClass(theme: Theme): string {
  return `theme-${theme}`;
}

/** Point `<meta name="theme-color">` at the theme's page ground. */
export function applyThemeColor(theme: Theme): void {
  if (typeof document === "undefined") return;
  let meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (!meta) {
    meta = document.createElement("meta");
    meta.name = "theme-color";
    document.head.appendChild(meta);
  }
  meta.content = THEME_PAGE_BG[theme];
}

/** Swap the theme class on <html>. No-op on the server. */
export function applyThemeClass(theme: Theme): void {
  if (typeof document === "undefined") return;
  const classes = document.documentElement.classList;
  for (const key of THEME_KEYS) classes.remove(themeClass(key));
  classes.add(themeClass(theme));
  applyThemeColor(theme);
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
)});var v=${JSON.stringify(THEME_KEYS)};var g=${JSON.stringify(
  THEME_PAGE_BG,
)};if(t&&v.indexOf(t)>=0){var c=document.documentElement.classList;v.forEach(function(k){c.remove('theme-'+k)});c.add('theme-'+t);var m=document.querySelector('meta[name="theme-color"]');if(!m){m=document.createElement('meta');m.name='theme-color';document.head.appendChild(m);}m.content=g[t];}}catch(e){}})();`;
