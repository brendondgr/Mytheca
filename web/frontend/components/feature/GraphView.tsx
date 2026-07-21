"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getScenarioGraph } from "@/lib/api";
import type { ScenarioGraph } from "@/lib/types";
import { graphLegend } from "@/lib/graphColors";
import { GraphCanvas } from "@/components/feature/GraphCanvas";

type Status = "loading" | "error" | "ready";

/**
 * The story-player's Graph view: the scenario's Story-Graph rendered as a
 * force-directed canvas, with a color legend and an sr-only tabular alternative.
 *
 * Fetches `getScenarioGraph` on mount, so nothing is requested (and the force
 * library's chunk is not loaded) until a scene is actually switched to Graph
 * mode. Degrades to a friendly state when Neo4j is off (`available:false`) or
 * the subgraph is empty.
 */
export function GraphView({ scenarioId }: { scenarioId: string }) {
  const [status, setStatus] = useState<Status>("loading");
  const [graph, setGraph] = useState<ScenarioGraph | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getScenarioGraph(scenarioId)
      .then((g) => {
        if (cancelled) return;
        setGraph(g);
        setStatus("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [scenarioId, nonce]);

  // Re-fetch: flip back to the loading state and bump the effect's nonce.
  const retry = useCallback(() => {
    setStatus("loading");
    setNonce((n) => n + 1);
  }, []);

  const nameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const n of graph?.nodes ?? []) map.set(n.id, n.label ?? n.id);
    return map;
  }, [graph]);

  const legend = useMemo(
    () => graphLegend(graph?.nodes ?? [], graph?.edges ?? []),
    [graph],
  );

  const shell = "flex min-w-0 flex-1 flex-col bg-page";

  if (status === "loading") {
    return (
      <section aria-label="Story graph" className={shell}>
        <div
          className="flex flex-1 items-center justify-center font-mono text-[11px] tracking-[0.16em] text-mute uppercase"
          role="status"
        >
          ❖ Reading the story graph…
        </div>
      </section>
    );
  }

  if (status === "error") {
    return (
      <section aria-label="Story graph" className={shell}>
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
          <p role="alert" className="max-w-[420px] font-body text-body-sm text-danger">
            The story graph could not be loaded.
          </p>
          <button
            type="button"
            onClick={retry}
            className="rounded-[2px] border border-field-bd px-[12px] py-[6px] font-mono text-[10px] tracking-[0.12em] text-ink uppercase hover:bg-hover hover:border-hair-strong"
          >
            Try again
          </button>
        </div>
      </section>
    );
  }

  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];

  // Neo4j disabled / unreachable — a calm, explanatory state (the graph is
  // optional infrastructure), not an error.
  if (!graph?.available) {
    return (
      <section aria-label="Story graph" className={shell}>
        <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
          <p className="font-display text-[18px] text-ink">The Story Graph is offline</p>
          <p className="max-w-[440px] font-body text-body-sm text-ink-soft">
            The graph database isn&apos;t running for this session, so relationships
            can&apos;t be drawn right now. The scene itself is unaffected — switch back to
            Chat to keep playing.
          </p>
        </div>
      </section>
    );
  }

  if (nodes.length === 0) {
    return (
      <section aria-label="Story graph" className={shell}>
        <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
          <p className="font-display text-[18px] text-ink">This scene&apos;s graph is empty</p>
          <p className="max-w-[440px] font-body text-body-sm text-ink-soft">
            Characters, settings, and the ties between them appear here as the world
            fills in.
          </p>
        </div>
      </section>
    );
  }

  const descId = "story-graph-desc";
  return (
    <section aria-label="Story graph" className={shell}>
      {/* Screen-reader + keyboard alternative: a summary and a full node/edge table. */}
      <p id={descId} className="sr-only">
        Story graph with {nodes.length} node{nodes.length === 1 ? "" : "s"} and {edges.length}{" "}
        connection{edges.length === 1 ? "" : "s"}. Nodes and edges are colored by type; the
        legend and the tables below list them.
      </p>
      <div className="sr-only">
        <table>
          <caption>Story-graph nodes</caption>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Type</th>
            </tr>
          </thead>
          <tbody>
            {nodes.map((n) => (
              <tr key={n.id}>
                <td>{n.label ?? n.id}</td>
                <td>{n.type ?? "Untyped"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <table>
          <caption>Story-graph connections</caption>
          <thead>
            <tr>
              <th scope="col">From</th>
              <th scope="col">Relationship</th>
              <th scope="col">To</th>
            </tr>
          </thead>
          <tbody>
            {edges.map((e, i) => (
              <tr key={`${e.source}-${e.type}-${e.target}-${i}`}>
                <td>{nameById.get(e.source) ?? e.source}</td>
                <td>{e.type}</td>
                <td>{nameById.get(e.target) ?? e.target}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* The canvas, labeled by the summary so SR users hear it before the tables. */}
      <figure
        role="img"
        aria-labelledby={descId}
        className="relative m-0 min-h-0 flex-1 focus-visible:outline-none"
        tabIndex={0}
      >
        <GraphCanvas nodes={nodes} edges={edges} />
      </figure>

      {/* Visible legend — type label + swatch, never color alone. */}
      <div
        data-testid="graph-legend"
        className="flex flex-none flex-wrap items-center gap-x-4 gap-y-2 border-t border-hair-strong bg-surface px-4 py-[10px]"
      >
        <span className="font-mono text-[9px] tracking-[0.16em] text-mute2 uppercase">Legend</span>
        {legend.map((item) => (
          <span
            key={`${item.kind}:${item.type}`}
            className="flex items-center gap-[6px] font-mono text-[10px] tracking-[0.08em] text-ink-soft"
          >
            <span
              aria-hidden
              className={item.kind === "node" ? "h-[10px] w-[10px] rounded-full" : "h-[3px] w-[14px] rounded-full"}
              style={{ background: item.color }}
            />
            {item.type}
          </span>
        ))}
      </div>
    </section>
  );
}
