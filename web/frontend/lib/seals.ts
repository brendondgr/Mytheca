// The storyline "seal": a simple shape glyph + color shown left of a storyline's
// name (in the header switcher) and chosen in the create/edit modal. Kept tiny
// and dependency-light so both the menu and the modal can import it.

import { PALETTE } from "@/lib/seed-data";

/** Simple, single-glyph shapes offered for a storyline seal. */
export const SEAL_SYMBOLS = ["◆", "●", "■", "▲", "★", "✦", "◇", "✚"];

/** Historical default seal: a gold diamond (matches the backend defaults). */
export const DEFAULT_SEAL_SYMBOL = "◆";
export const DEFAULT_SEAL_COLOR = "#C8862A";

/** Seal colors offered in the picker — gold first, then the accent palette. */
export const SEAL_COLORS = [DEFAULT_SEAL_COLOR, ...PALETTE];
