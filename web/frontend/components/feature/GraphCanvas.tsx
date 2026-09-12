"use client";

import { useEffect, useMemo, useRef, useState, type ComponentType, type MutableRefObject } from "react";
import dynamic from "next/dynamic";
import type {
  ForceGraphMethods,
  ForceGraphProps,
  LinkObject,
  NodeObject,
} from "react-force-graph-2d";
import type { GraphEdge, GraphNode } from "@/lib/types";
import { edgeColor, nodeColor } from "@/lib/graphColors";
import { useTheme } from "@/hooks/use-theme";

// The renderer mutates node objects (adds x/y/vx/vy) and rewrites link
// source/target into node refs, so we feed it fresh copies keyed by name/type.
// Each carries its source `GraphNode`/`GraphEdge` so click handlers can report
// the full element (with its metadata) without a lookup.
interface RFNode {
  id: string;
  name: string;
  type: string | null;
  node: GraphNode;
  x?: number;
  y?: number;
}
interface RFLink {
  source: string;
  target: string;
  type: string;
  edge: GraphEdge;
}

/** The renderer's imperative handle, as this component's node/link types see it. */
type GraphHandle = ForceGraphMethods<NodeObject<RFNode>, LinkObject<RFNode, RFLink>>;

type GraphProps = ForceGraphProps<RFNode, RFLink> & {
  graphRef?: MutableRefObject<GraphHandle | undefined>;
};

/**
 * How much of a node's label the canvas draws.
 *
 * A `Character` or `Setting` label is a name and is always short. An `Event` label is the
 * gloss of something that happened and an authored `Secret` is a whole clause, so a
 * well-played world draws dozens of sentence-length labels over each other and the graph
 * stops being readable at exactly the point it becomes interesting. The full text stays on
 * the node's hover tooltip, which is where a reader who wants it is already looking.
 */
const LABEL_MAX = 30;

export function shortLabel(name: string): string {
  return name.length > LABEL_MAX ? `${name.slice(0, LABEL_MAX - 1).trimEnd()}…` : name;
}

/** A stable identity for an edge (there can be several between two nodes). */
export function edgeKey(e: { source: string; target: string; type: string }): string {
  return `${e.source}|${e.target}|${e.type}`;
}

// react-force-graph-2d reads `window` at import time, so it can only load in the
// browser — `ssr:false`. Because this is the *only* module importing it, the
// dynamic() split also keeps the library (and d3-force) out of the initial
// bundle: it is fetched the first time a scene is switched to Graph mode. The
// dynamic() wrapper erases the component's generics, so we re-apply our node/
// link types here to keep the accessor callbacks typed.
// `next/dynamic` does not forward refs, and the zoom-to-fit below needs the graph
// instance — so the loader wraps the real component and hands the ref through as a
// plain prop. Everything else is passed straight down.
const ForceGraph2D = dynamic(
  async () => {
    const Inner = (await import("react-force-graph-2d")).default;
    function ForceGraphWithRef({ graphRef, ...props }: GraphProps) {
      return <Inner ref={graphRef} {...props} />;
    }
    return ForceGraphWithRef;
  },
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full w-full items-center justify-center font-mono text-eyebrow tracking-[0.12em] text-mute2 uppercase">
        ❖ Loading graph…
      </div>
    ),
  },
) as unknown as ComponentType<GraphProps>;

/** Read a themed hex from a CSS custom property on <html>. */
function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/**
 * The force-directed canvas itself. Isolated so the heavy library stays lazy and
 * so `GraphView` (and its tests) never touch the canvas. Nodes are colored by
 * type, labels are drawn in the live theme ink color, edges by relationship
 * valence. Clicking a node/edge reports the full element (`onNodeSelect`/
 * `onEdgeSelect`); clicking the background clears (`onBackgroundClick`). The
 * currently-selected node/edge (`selectedNodeId`/`selectedEdgeKey`) is drawn
 * emphasized.
 */
export function GraphCanvas({
  nodes,
  edges,
  onNodeSelect,
  onEdgeSelect,
  onBackgroundClick,
  selectedNodeId = null,
  selectedEdgeKey = null,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeSelect?: (node: GraphNode) => void;
  onEdgeSelect?: (edge: GraphEdge) => void;
  onBackgroundClick?: () => void;
  selectedNodeId?: string | null;
  selectedEdgeKey?: string | null;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState<{ w: number; h: number } | null>(null);
  const hoverId = useRef<string | null>(null);
  const graphRef = useRef<GraphHandle | undefined>(undefined);
  const { theme } = useTheme(); // subscribe so a theme switch re-renders + repaints

  // Re-read the themed draw colors (label ink + halo) on every render; reading
  // `theme` here makes the switch a real input, so the canvas repaints in the
  // new theme's colors. (`theme` is always a truthy Theme string.)
  const ink = theme ? cssVar("--ink", "#241b10") : "#241b10";
  const halo = theme ? cssVar("--card-bg", "#f4ecda") : "#f4ecda";

  // Measure the wrapper — the canvas needs explicit pixel dimensions. Take an
  // initial synchronous measurement (so the canvas mounts even if the first
  // ResizeObserver callback is delayed), then track later resizes with RO.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = (w: number, h: number) => {
      if (w > 0 && h > 0) setDims((prev) => (prev && prev.w === w && prev.h === h ? prev : { w, h }));
    };
    measure(Math.round(el.clientWidth), Math.round(el.clientHeight));
    const ro = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (box) measure(Math.round(box.width), Math.round(box.height));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const data = useMemo(
    () => ({
      nodes: nodes.map<RFNode>((n) => ({ id: n.id, name: n.label ?? n.id, type: n.type, node: n })),
      links: edges.map<RFLink>((e) => ({
        source: e.source,
        target: e.target,
        type: e.type,
        edge: e,
      })),
    }),
    [nodes, edges],
  );

  return (
    <div ref={wrapRef} className="h-full w-full">
      {dims && dims.w > 0 && dims.h > 0 ? (
        <ForceGraph2D
          width={dims.w}
          height={dims.h}
          graphData={data}
          backgroundColor="rgba(0,0,0,0)"
          nodeRelSize={5}
          nodeLabel={(n: RFNode) => `${n.name}${n.type ? ` — ${n.type}` : ""}`}
          linkColor={(l: RFLink) => edgeColor(l.type)}
          linkWidth={(l: RFLink) => (edgeKey(l.edge) === selectedEdgeKey ? 3 : 1)}
          graphRef={graphRef}
          warmupTicks={20}
          cooldownTicks={120}
          cooldownTime={4000}
          // Frame the whole graph once the layout settles. Without this the view sits at
          // zoom 1 around the origin, which reads as a small knot adrift in a large empty
          // canvas — and gets worse, not better, the more the graph has in it.
          onEngineStop={() => graphRef.current?.zoomToFit(400, 48)}
          onNodeHover={(n: RFNode | null) => {
            hoverId.current = n?.id ?? null;
          }}
          onNodeClick={(n: RFNode) => {
            onNodeSelect?.(n.node);
          }}
          onLinkClick={(l: RFLink) => {
            onEdgeSelect?.(l.edge);
          }}
          onBackgroundClick={() => {
            onBackgroundClick?.();
          }}
          nodeCanvasObjectMode={() => "replace"}
          nodeCanvasObject={(n: RFNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
            const x = n.x ?? 0;
            const y = n.y ?? 0;
            const r = 5;
            const fill = nodeColor(n.type);
            const selected = n.id === selectedNodeId;
            // A persistent selection ring (thicker), or a lighter hover ring —
            // both a constant screen thickness regardless of zoom.
            if (selected || hoverId.current === n.id) {
              ctx.beginPath();
              ctx.arc(x, y, r + (selected ? 4 : 3) / globalScale, 0, Math.PI * 2);
              ctx.strokeStyle = fill;
              ctx.lineWidth = (selected ? 2.5 : 1.5) / globalScale;
              ctx.stroke();
            }
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.fillStyle = fill;
            ctx.fill();
            // Label below the node, kept a constant screen size, with a soft halo
            // stroke so it reads over both edges and the parchment/dark ground.
            const fontSize = 12 / globalScale;
            ctx.font = `${fontSize}px "IBM Plex Mono", ui-monospace, monospace`;
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            const ly = y + r + 2 / globalScale;
            ctx.lineWidth = 3 / globalScale;
            ctx.strokeStyle = halo;
            const label = shortLabel(n.name);
            ctx.strokeText(label, x, ly);
            ctx.fillStyle = ink;
            ctx.fillText(label, x, ly);
          }}
        />
      ) : null}
    </div>
  );
}

export default GraphCanvas;
