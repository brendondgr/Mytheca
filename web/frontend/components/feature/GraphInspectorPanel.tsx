"use client";

import { useMemo } from "react";
import type { GraphEdge, GraphNode } from "@/lib/types";
import { edgeColor, graphTypeCounts, nodeColor, type TypeCount } from "@/lib/graphColors";

/** What the inspector is currently focused on: a node, an edge, or nothing. */
export type GraphSelection =
  | { kind: "node"; node: GraphNode }
  | { kind: "edge"; edge: GraphEdge }
  | null;

/** Turn a metadata value into a readable string. */
function fmtValue(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

/** A colored, labeled type badge (color is paired with the type text). */
function TypeBadge({ type, color }: { type: string; color: string }) {
  return (
    <span
      className="inline-flex items-center gap-xs rounded-full border px-sm py-3xs font-mono text-eyebrow tracking-[0.12em] uppercase"
      style={{ borderColor: color, color }}
    >
      <span aria-hidden className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: color }} />
      {type}
    </span>
  );
}

/** A `<dl>` of an element's metadata (label + wrapped value); handles empty. */
function PropertyList({ metadata }: { metadata: Record<string, unknown> }) {
  const entries = Object.entries(metadata ?? {});
  if (entries.length === 0) {
    return <p className="font-body text-body-sm text-mute2">No further properties.</p>;
  }
  return (
    <dl className="flex flex-col gap-sm">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt className="font-mono text-eyebrow tracking-[0.14em] text-mute2 uppercase">
            {key.replace(/[_-]+/g, " ")}
          </dt>
          <dd className="mt-3xs font-body text-body-sm leading-[1.4] break-words text-ink">
            {fmtValue(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** The small-caps section header used across the overview. */
function SectionHead({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-sm border-b border-hair pb-2xs font-mono text-eyebrow tracking-[0.16em] text-mute uppercase">
      {children}
    </h3>
  );
}

/** One breakdown row: swatch + type + count. */
function BreakdownRow({ item }: { item: TypeCount }) {
  return (
    <li className="flex items-center justify-between gap-2 py-3xs">
      <span className="flex min-w-0 items-center gap-sm">
        <span aria-hidden className="h-[10px] w-[10px] flex-none rounded-full" style={{ background: item.color }} />
        <span className="truncate font-body text-body-sm text-ink-soft">{item.type}</span>
      </span>
      <span className="flex-none font-mono text-eyebrow text-ink">{item.count}</span>
    </li>
  );
}

const BACK_BTN =
  "mb-md inline-flex items-center gap-2xs rounded-xs border border-field-bd px-sm py-2xs font-mono text-eyebrow tracking-[0.12em] text-mute uppercase hover:bg-hover hover:text-ink hover:border-hair-strong focus-visible:border-accent focus-visible:text-accent-ink";

/**
 * The Graph-mode right rail. With nothing selected it shows the **overview** —
 * the node-type and edge-type breakdown (color · type · count). Selecting a node
 * or edge in the canvas switches it to a **detail** view of that element's
 * properties (its metadata), with a Back button to return to the overview. This
 * is an author-facing diagnostic, so it shows every property the graph carries.
 */
export function GraphInspectorPanel({
  nodes,
  edges,
  selection,
  onClear,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selection: GraphSelection;
  onClear: () => void;
}) {
  const nameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const n of nodes) map.set(n.id, n.label ?? n.id);
    return map;
  }, [nodes]);

  const breakdown = useMemo(() => graphTypeCounts(nodes, edges), [nodes, edges]);

  const shell =
    "mytheca-rail hidden w-[288px] flex-none overflow-auto border-l border-hair-strong p-[18px_16px] lg:block";

  // ---- Node detail -------------------------------------------------------
  if (selection?.kind === "node") {
    const n = selection.node;
    const color = nodeColor(n.type);
    return (
      <aside aria-label="Graph inspector" data-testid="graph-inspector" className={shell}>
        <button type="button" onClick={onClear} className={BACK_BTN}>
          ‹ Overview
        </button>
        <h2 className="font-display text-step-1 leading-tight text-ink">{n.label ?? n.id}</h2>
        <div className="mt-sm flex flex-wrap items-center gap-2">
          <TypeBadge type={n.type ?? "Untyped"} color={color} />
        </div>
        <p className="mt-xs font-mono text-eyebrow tracking-[0.06em] text-mute2 break-all">id: {n.id}</p>
        <hr className="my-lg border-hair" />
        <PropertyList metadata={n.metadata} />
      </aside>
    );
  }

  // ---- Edge detail -------------------------------------------------------
  if (selection?.kind === "edge") {
    const e = selection.edge;
    const color = edgeColor(e.type);
    return (
      <aside aria-label="Graph inspector" data-testid="graph-inspector" className={shell}>
        <button type="button" onClick={onClear} className={BACK_BTN}>
          ‹ Overview
        </button>
        <div className="flex items-center gap-2">
          <TypeBadge type={e.type} color={color} />
        </div>
        <p className="mt-sm font-body text-body-sm text-ink">
          <span className="font-semibold">{nameById.get(e.source) ?? e.source}</span>
          <span className="px-xs text-mute" aria-hidden>
            →
          </span>
          <span className="font-semibold">{nameById.get(e.target) ?? e.target}</span>
        </p>
        <hr className="my-lg border-hair" />
        <PropertyList metadata={e.metadata} />
      </aside>
    );
  }

  // ---- Overview (nothing selected) ---------------------------------------
  return (
    <aside aria-label="Graph inspector" data-testid="graph-inspector" className={shell}>
      <h2 className="mb-2xs font-display text-body text-ink">Story Graph</h2>
      <p className="mb-lg font-mono text-eyebrow tracking-[0.1em] text-mute2 uppercase">
        {nodes.length} node{nodes.length === 1 ? "" : "s"} · {edges.length} connection
        {edges.length === 1 ? "" : "s"}
      </p>

      <section className="mb-lg">
        <SectionHead>Node types</SectionHead>
        <ul>
          {breakdown.nodes.map((item) => (
            <BreakdownRow key={item.type} item={item} />
          ))}
        </ul>
      </section>

      <section className="mb-lg">
        <SectionHead>Edge types</SectionHead>
        {breakdown.edges.length > 0 ? (
          <ul>
            {breakdown.edges.map((item) => (
              <BreakdownRow key={item.type} item={item} />
            ))}
          </ul>
        ) : (
          <p className="font-body text-body-sm text-mute2">No connections yet.</p>
        )}
      </section>

      <p className="font-body text-body-sm leading-[1.4] text-mute2">
        Select a node or edge in the graph to see its properties.
      </p>
    </aside>
  );
}
