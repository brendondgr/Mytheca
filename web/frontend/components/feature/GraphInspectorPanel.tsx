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
      className="inline-flex items-center gap-[6px] rounded-full border px-[8px] py-[2px] font-mono text-[9px] tracking-[0.12em] uppercase"
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
    <dl className="flex flex-col gap-[10px]">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt className="font-mono text-[9px] tracking-[0.14em] text-mute2 uppercase">
            {key.replace(/[_-]+/g, " ")}
          </dt>
          <dd className="mt-[2px] font-body text-body-sm leading-[1.4] break-words text-ink">
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
    <h3 className="mb-[8px] border-b border-hair pb-[4px] font-mono text-[9px] tracking-[0.16em] text-mute uppercase">
      {children}
    </h3>
  );
}

/** One breakdown row: swatch + type + count. */
function BreakdownRow({ item }: { item: TypeCount }) {
  return (
    <li className="flex items-center justify-between gap-2 py-[3px]">
      <span className="flex min-w-0 items-center gap-[8px]">
        <span aria-hidden className="h-[10px] w-[10px] flex-none rounded-full" style={{ background: item.color }} />
        <span className="truncate font-body text-body-sm text-ink-soft">{item.type}</span>
      </span>
      <span className="flex-none font-mono text-[11px] text-ink">{item.count}</span>
    </li>
  );
}

const BACK_BTN =
  "mb-[12px] inline-flex items-center gap-[5px] rounded-[2px] border border-field-bd px-[9px] py-[5px] font-mono text-[9px] tracking-[0.12em] text-mute uppercase hover:bg-hover hover:text-ink hover:border-hair-strong focus-visible:border-accent focus-visible:text-accent";

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
        <h2 className="font-display text-[18px] leading-tight text-ink">{n.label ?? n.id}</h2>
        <div className="mt-[8px] flex flex-wrap items-center gap-2">
          <TypeBadge type={n.type ?? "Untyped"} color={color} />
        </div>
        <p className="mt-[6px] font-mono text-[10px] tracking-[0.06em] text-mute2 break-all">id: {n.id}</p>
        <hr className="my-[14px] border-hair" />
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
        <p className="mt-[10px] font-body text-body-sm text-ink">
          <span className="font-semibold">{nameById.get(e.source) ?? e.source}</span>
          <span className="px-[6px] text-mute" aria-hidden>
            →
          </span>
          <span className="font-semibold">{nameById.get(e.target) ?? e.target}</span>
        </p>
        <hr className="my-[14px] border-hair" />
        <PropertyList metadata={e.metadata} />
      </aside>
    );
  }

  // ---- Overview (nothing selected) ---------------------------------------
  return (
    <aside aria-label="Graph inspector" data-testid="graph-inspector" className={shell}>
      <h2 className="mb-[4px] font-display text-[16px] text-ink">Story Graph</h2>
      <p className="mb-[16px] font-mono text-[9px] tracking-[0.1em] text-mute2 uppercase">
        {nodes.length} node{nodes.length === 1 ? "" : "s"} · {edges.length} connection
        {edges.length === 1 ? "" : "s"}
      </p>

      <section className="mb-[18px]">
        <SectionHead>Node types</SectionHead>
        <ul>
          {breakdown.nodes.map((item) => (
            <BreakdownRow key={item.type} item={item} />
          ))}
        </ul>
      </section>

      <section className="mb-[18px]">
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
