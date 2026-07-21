/**
 * Story-Graph type → color mapping for the in-chat graph view.
 *
 * Nodes and edges are colored by their *type* (the Neo4j label / relationship
 * type), independent of the app theme, so the graph reads the same across
 * Parchment / Ember / Slate. The built-in Story-Graph types
 * (`docs/story-graph-neo4j.md`) get hand-tuned, mutually distinct colors; any
 * *unknown* type — a user-defined or future entity type — is assigned a stable,
 * distinct color from a deterministic hash of its name, so the map keeps working
 * as the graph grows to interconnect many more things without a code change.
 *
 * Each color clears the 3:1 non-text contrast bar (WCAG 1.4.11) against both the
 * light parchment and the near-black dark grounds; the legend
 * (`graphLegend`) pairs every color with its text label, so meaning never rests
 * on color alone (WCAG 1.4.1).
 */

/** Distinct colors for the six built-in node types (§5 of the type registry). */
const NODE_COLORS: Record<string, string> = {
  Character: "#B0492F", // ember red
  Setting: "#2F7D6B", // teal green
  Event: "#C56A1F", // amber
  Faction: "#6B4A8A", // violet
  Secret: "#B0506A", // rose
  Consequence: "#3A5A78", // steel blue
};

// Edges are grouped by valence (§1.3) so a relationship's felt direction reads
// at a glance: positive feelings/alliances green, hostility/negative red,
// structural/knowledge edges a neutral slate.
const EDGE_POSITIVE = "#1F8A5B"; // success green
const EDGE_NEGATIVE = "#9A3520"; // danger
const EDGE_NEUTRAL = "#5B6B7A"; // muted slate

const EDGE_COLORS: Record<string, string> = {
  // feelings (§5.1)
  loves: EDGE_POSITIVE,
  trusts: EDGE_POSITIVE,
  fears: EDGE_NEGATIVE,
  resents: EDGE_NEGATIVE,
  // relations (§5.5)
  allied_with: EDGE_POSITIVE,
  at_war_with: EDGE_NEGATIVE,
  // knowledge (§5.4)
  knows: EDGE_NEUTRAL,
  suspects: EDGE_NEUTRAL,
  member_of: EDGE_NEUTRAL,
  // structure (§4.3 / §4.4)
  from: EDGE_NEUTRAL,
  present_at: EDGE_NEUTRAL,
  controls: EDGE_NEUTRAL,
  claims: EDGE_NEUTRAL,
  connected_to: EDGE_NEUTRAL,
  occurred_at: EDGE_NEUTRAL,
  involved: EDGE_NEUTRAL,
  subject: EDGE_NEUTRAL,
};

/** Fallback color for a node/edge whose type is missing entirely. */
const UNTYPED = "#7A7266";

// A small FNV-1a hash — stable across runs and platforms (no Math.random), so a
// given type name always maps to the same color.
function hashString(input: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

// HSL → hex at a fixed saturation/lightness tuned to clear 3:1 on both grounds.
function hslToHex(hue: number, sat: number, light: number): string {
  const s = sat / 100;
  const l = light / 100;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((hue / 60) % 2) - 1));
  const m = l - c / 2;
  let r = 0;
  let g = 0;
  let b = 0;
  if (hue < 60) [r, g, b] = [c, x, 0];
  else if (hue < 120) [r, g, b] = [x, c, 0];
  else if (hue < 180) [r, g, b] = [0, c, x];
  else if (hue < 240) [r, g, b] = [0, x, c];
  else if (hue < 300) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  const to255 = (v: number) =>
    Math.round((v + m) * 255)
      .toString(16)
      .padStart(2, "0");
  return `#${to255(r)}${to255(g)}${to255(b)}`;
}

/** A stable, distinct color derived from any string (for unknown types). */
function colorFromName(name: string): string {
  const h = hashString(name);
  // Spread the hue across the wheel; keep S/L in the mid band so it stays
  // legible on parchment (light) and near-black (dark) alike.
  return hslToHex(h % 360, 52, 46);
}

/** Color for a node of the given Neo4j label/type (null → untyped gray). */
export function nodeColor(type: string | null | undefined): string {
  if (!type) return UNTYPED;
  return NODE_COLORS[type] ?? colorFromName(`node:${type}`);
}

/** Color for an edge of the given relationship type (empty → untyped gray). */
export function edgeColor(type: string | null | undefined): string {
  if (!type) return UNTYPED;
  return EDGE_COLORS[type] ?? colorFromName(`edge:${type}`);
}

export interface LegendItem {
  /** The node label or edge relationship type. */
  type: string;
  /** The color it is drawn in. */
  color: string;
  /** Which family it belongs to (drives the legend's grouping/label). */
  kind: "node" | "edge";
}

/**
 * The de-duplicated, sorted legend for a graph — one entry per distinct node
 * type and per distinct edge type actually present, each with its color. Nodes
 * first, then edges; alphabetical within each group. Untyped nodes/edges are
 * folded into a single "Untyped" entry rather than repeated.
 */
export function graphLegend(
  nodes: { type: string | null | undefined }[],
  edges: { type: string | null | undefined }[],
): LegendItem[] {
  const nodeTypes = new Set<string>();
  for (const n of nodes) nodeTypes.add(n.type || "Untyped");
  const edgeTypes = new Set<string>();
  for (const e of edges) edgeTypes.add(e.type || "Untyped");

  const nodeItems: LegendItem[] = [...nodeTypes]
    .sort((a, b) => a.localeCompare(b))
    .map((type) => ({
      type,
      color: nodeColor(type === "Untyped" ? null : type),
      kind: "node" as const,
    }));
  const edgeItems: LegendItem[] = [...edgeTypes]
    .sort((a, b) => a.localeCompare(b))
    .map((type) => ({
      type,
      color: edgeColor(type === "Untyped" ? null : type),
      kind: "edge" as const,
    }));
  return [...nodeItems, ...edgeItems];
}
