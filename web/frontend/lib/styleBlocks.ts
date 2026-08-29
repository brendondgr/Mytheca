/**
 * Where each style block's live value actually comes from.
 *
 * Mirrors the backend rule in `services/style_guide.resolve`: **two layers, not three** —
 * `storyline → scenario`, and the last non-blank value wins. There is deliberately no
 * global layer here, unlike `promptLayers`, because a global style guide would push one
 * voice onto every world. Saved presets are a *library, not a layer*: applying one copies
 * its text into a storyline's own fields.
 *
 * That last word — non-*blank* — is the whole subtlety, and it is the same one
 * `promptLayers` carries: a block present at a layer with an empty value means *inherit the
 * layer below*, not *override with nothing*. Getting it backwards would make a cleared field
 * look like a customisation.
 *
 * This is a pure mirror of a backend rule, which means it can drift from it. The rule is a
 * few lines and is pinned by `utils/tests/backend/services/test_style_guide.py`; the
 * alternative is a round-trip per keystroke in an editor whose entire job is to show what a
 * value would resolve to.
 */

/** The layers, in precedence order — later beats earlier. */
export type StyleLayer = "none" | "storyline" | "scenario";

/** Player-facing names. They name the *place*, not the implementation. */
export const STYLE_LAYER_LABELS: Record<StyleLayer, string> = {
  none: "Not set",
  storyline: "This world",
  scenario: "This scene",
};

export interface StyleLayerInputs {
  storyline?: Record<string, string> | null;
  scenario?: Record<string, string> | null;
}

/** Trimmed, or `""` — the one place "is this block set?" is decided on the client. */
function value(map: Record<string, string> | null | undefined, id: string): string {
  return (map?.[id] ?? "").trim();
}

/**
 * For every id in `catalog`, which layer supplies its live value.
 *
 * A block nobody has set resolves to `"none"` rather than being omitted, so the editor can
 * say "Not set" instead of rendering a chip-shaped gap.
 */
export function resolveStyleLayers(
  catalog: string[],
  { storyline, scenario }: StyleLayerInputs,
): Record<string, StyleLayer> {
  const out: Record<string, StyleLayer> = {};
  for (const id of catalog) {
    if (value(scenario, id)) out[id] = "scenario";
    else if (value(storyline, id)) out[id] = "storyline";
    else out[id] = "none";
  }
  return out;
}

/**
 * The text a block would resolve to at this layer's *baseline* — i.e. what the author sees
 * if they clear the field. Empty when nothing below has set it.
 */
export function inheritedValue(
  id: string,
  { storyline }: StyleLayerInputs,
): string {
  return value(storyline, id);
}

/**
 * Strip a draft down to what should actually be stored: trimmed, blanks dropped.
 *
 * The backend canonicalises on write too, and that is not redundant — this is what makes
 * the editor's dirty check honest. Without it, typing a space into an empty field would
 * mark the guide unsaved and then save nothing.
 */
export function packBlocks(draft: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [id, text] of Object.entries(draft)) {
    const trimmed = (text ?? "").trim();
    if (trimmed) out[id] = trimmed;
  }
  return out;
}

/** Whether two block maps would store identically — the editor's dirty check. */
export function sameBlocks(
  a: Record<string, string>,
  b: Record<string, string>,
): boolean {
  const left = packBlocks(a);
  const right = packBlocks(b);
  const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
  for (const key of keys) if (left[key] !== right[key]) return false;
  return true;
}
