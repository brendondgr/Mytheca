// The storyline "seal": a simple shape glyph + color shown left of a storyline's
// name (in the header switcher) and chosen in the SealModal pop-up. Kept tiny and
// dependency-light so both the menu and the modal can import it.

/**
 * Single-glyph shapes offered for a storyline seal (~3× the original eight).
 * All render in the brand fonts as plain text — no icon dependency.
 */
export const SEAL_SYMBOLS = [
  "◆", "◇", "●", "○", "■", "□",
  "▲", "△", "▼", "◀", "★", "☆",
  "✦", "✧", "✶", "❖", "✚", "✜",
  "⬟", "⬢", "♦", "☾", "☀", "⚜",
];

/** Historical default seal: a gold diamond (matches the backend defaults). */
export const DEFAULT_SEAL_SYMBOL = "◆";
export const DEFAULT_SEAL_COLOR = "#C8862A";

/**
 * Curated seal swatches — gold first, then ember/jewel tones and neutrals. The
 * SealModal also offers a free color wheel for anything outside this set.
 */
export const SEAL_COLORS = [
  DEFAULT_SEAL_COLOR, // gold
  "#E0B341", // bright gold
  "#8E2B1C", // ember red
  "#C0392B", // crimson
  "#C56A1F", // burnt orange
  "#B0506A", // rose
  "#8E3B7A", // violet
  "#6B4A8A", // purple
  "#3A5A78", // steel blue
  "#2C8E8E", // teal
  "#2F7D6B", // deep teal
  "#1F8A5B", // green
  "#7E8A2B", // olive
  "#5A534A", // taupe
  "#9A9488", // stone
  "#D8CDB8", // parchment
  "#2A2622", // ink
];
