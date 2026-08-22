/**
 * Where each writing prompt's live value actually comes from.
 *
 * Mirrors the backend precedence in `prompt_registry.resolve_prompts`: start from the
 * registry default, then apply `global → storyline → scenario` in order, and **the last
 * non-blank value wins**. That last word is the whole subtlety — a key present at a layer
 * with an empty (or whitespace-only) value means *inherit the layer below*, not *override
 * with nothing*. Getting that backwards would make a cleared field look like a customisation.
 *
 * This is a pure mirror of a backend rule, which means it can drift from it. The rule is
 * four lines and has been stable since the override system shipped; the alternative is a
 * round-trip per keystroke in an editor whose whole job is to show what a value would
 * resolve to.
 */

/** The layers, in precedence order — later beats earlier. */
export type PromptLayer = "default" | "global" | "storyline" | "scenario";

/** Player-facing names. `global` is "Everywhere" because "global" is an implementation word. */
export const PROMPT_LAYER_LABELS: Record<PromptLayer, string> = {
  default: "Default",
  global: "Everywhere",
  storyline: "This world",
  scenario: "This scene",
};

export interface PromptLayerInputs {
  global?: Record<string, string> | null;
  storyline?: Record<string, string> | null;
  scenario?: Record<string, string> | null;
}

/**
 * For every key in `catalog`, which layer supplies its live value.
 *
 * `catalog` is the set of known prompt keys — an override for a key nobody knows about is
 * ignored, exactly as the backend ignores it, so a stale stored key cannot make the UI
 * claim a customisation that will never be applied.
 */
export function resolveLayers(
  catalog: readonly string[],
  layers: PromptLayerInputs,
): Record<string, PromptLayer> {
  const out: Record<string, PromptLayer> = {};
  for (const key of catalog) out[key] = "default";

  const ordered: [PromptLayer, Record<string, string> | null | undefined][] = [
    ["global", layers.global],
    ["storyline", layers.storyline],
    ["scenario", layers.scenario],
  ];

  for (const [name, layer] of ordered) {
    if (!layer) continue;
    for (const [key, value] of Object.entries(layer)) {
      if (!(key in out)) continue; // unknown key — the backend ignores it too
      if (typeof value !== "string" || !value.trim()) continue; // blank = inherit
      out[key] = name;
    }
  }
  return out;
}
