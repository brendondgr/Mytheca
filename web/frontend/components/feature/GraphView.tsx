"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getScenarioGraph } from "@/lib/api";
import type { ScenarioGraph } from "@/lib/types";
import { GraphCanvas, edgeKey } from "@/components/feature/GraphCanvas";
import { GraphInspectorPanel, type GraphSelection } from "@/components/feature/GraphInspectorPanel";
import { useDelayedFlag } from "@/hooks/use-delayed-flag";
import { SKELETON_TIMEOUT_MS } from "@/components/ui/Skeleton";

type Status = "loading" | "error" | "ready";

/** The shared frame for the graph's four non-canvas states, so a stalled load,
 *  a failure, an offline database, and an empty graph all read as one system. */
function GraphMessage({
  title,
  body,
  onRetry,
  role,
}: {
  title: string;
  body: string;
  onRetry?: () => void;
  role?: "alert";
}) {
  return (
    <div
      role={role}
      className="content-enter flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center"
    >
      <p className="font-display text-[18px] text-ink">
        <span aria-hidden className="mr-[6px] text-gold">
          ❖
        </span>
        {title}
      </p>
      <p className="max-w-[440px] font-body text-body-sm leading-[1.5] text-ink-soft">{body}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="press touch-target mt-[4px] cursor-pointer rounded-[2px] border border-field-bd px-[12px] py-[6px] font-mono text-[10px] tracking-[0.12em] text-ink uppercase transition-colors duration-fast ease-soft hover:border-hair-strong hover:bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          Try again
        </button>
      ) : null}
    </div>
  );
}

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
  const [selection, setSelection] = useState<GraphSelection>(null);

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

  const isLoading = status === "loading";
  const showLoading = useDelayedFlag(isLoading);
  const stalled = useDelayedFlag(isLoading, SKELETON_TIMEOUT_MS);

  const clearSelection = useCallback(() => setSelection(null), []);
  const selectedNodeId = selection?.kind === "node" ? selection.node.id : null;
  const selectedEdgeKey = selection?.kind === "edge" ? edgeKey(selection.edge) : null;

  const shell = "flex min-w-0 flex-1 flex-col bg-page";

  if (status === "loading") {
    // A graph canvas has no internal layout to trace, so there is no honest
    // skeleton to draw for it — a rectangle of shimmer would promise a shape
    // the force simulation does not have. The status line is the right answer
    // here; what it needed was the 300ms gate (a warm graph returns fast
    // enough that the line was pure flicker) and a ceiling, so an unreachable
    // Neo4j cannot leave it reading forever.
    if (!showLoading) return <section aria-label="Story graph" className={shell} aria-busy="true" />;
    if (stalled) {
      return (
        <section aria-label="Story graph" className={shell}>
          <GraphMessage
            role="alert"
            title="The story graph is taking too long"
            body="The graph database hasn't answered. It may be starting up, or unreachable."
            onRetry={retry}
          />
        </section>
      );
    }
    return (
      <section aria-label="Story graph" className={shell} aria-busy="true">
        <div
          className="content-enter flex flex-1 items-center justify-center font-mono text-[11px] tracking-[0.16em] text-mute uppercase"
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
        <GraphMessage
          role="alert"
          title="The story graph could not be loaded"
          body="The request to the graph database failed. The scene itself is unaffected."
          onRetry={retry}
        />
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
        <GraphMessage
          title="The Story Graph is offline"
          body="The graph database isn't running for this session, so relationships can't be drawn right now. The scene itself is unaffected — switch back to Chat to keep playing."
        />
      </section>
    );
  }

  if (nodes.length === 0) {
    return (
      <section aria-label="Story graph" className={shell}>
        <GraphMessage
          title="This scene's graph is empty"
          body="Characters, settings, and the ties between them appear here as the world fills in. Play a turn and come back — the graph is written as the scene happens."
        />
      </section>
    );
  }

  const descId = "story-graph-desc";
  return (
    <>
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
        <GraphCanvas
          nodes={nodes}
          edges={edges}
          selectedNodeId={selectedNodeId}
          selectedEdgeKey={selectedEdgeKey}
          onNodeSelect={(node) => setSelection({ kind: "node", node })}
          onEdgeSelect={(edge) => setSelection({ kind: "edge", edge })}
          onBackgroundClick={clearSelection}
        />
      </figure>
    </section>

    {/* Right rail: the type breakdown, or the selected node/edge's properties. */}
    <GraphInspectorPanel nodes={nodes} edges={edges} selection={selection} onClear={clearSelection} />
    </>
  );
}
