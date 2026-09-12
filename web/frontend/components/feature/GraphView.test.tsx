import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ScenarioGraph } from "@/lib/types";

const getScenarioGraph = vi.fn();
vi.mock("@/lib/api", () => ({
  getScenarioGraph: (...args: unknown[]) => getScenarioGraph(...args),
}));

// Stub the heavy canvas renderer — GraphView's contract is the state machine,
// the accessible table, and wiring selection to the inspector, not the drawing.
// The stub exposes the current selection (data-*) and buttons that fire the
// selection callbacks, so we can drive selection without a real canvas.
vi.mock("@/components/feature/GraphCanvas", () => ({
  edgeKey: (e: { source: string; target: string; type: string }) => `${e.source}|${e.target}|${e.type}`,
  GraphCanvas: ({
    nodes,
    edges,
    onNodeSelect,
    onEdgeSelect,
    onBackgroundClick,
    selectedNodeId,
    selectedEdgeKey,
  }: {
    nodes: { id: string }[];
    edges: unknown[];
    onNodeSelect?: (n: unknown) => void;
    onEdgeSelect?: (e: unknown) => void;
    onBackgroundClick?: () => void;
    selectedNodeId?: string | null;
    selectedEdgeKey?: string | null;
  }) => (
    <div data-testid="graph-canvas" data-selected-node={selectedNodeId ?? ""} data-selected-edge={selectedEdgeKey ?? ""}>
      canvas:{nodes.length}:{edges.length}
      <button type="button" onClick={() => onNodeSelect?.(nodes[0])}>
        select-node
      </button>
      <button type="button" onClick={() => onEdgeSelect?.(edges[0])}>
        select-edge
      </button>
      <button type="button" onClick={() => onBackgroundClick?.()}>
        bg-click
      </button>
    </div>
  ),
}));

import { GraphView } from "@/components/feature/GraphView";

function graph(partial: Partial<ScenarioGraph>): ScenarioGraph {
  return { available: true, scenarioId: "sc1", anchorIds: [], nodes: [], edges: [], ...partial };
}

const POPULATED = graph({
  nodes: [
    { id: "c1", type: "Character", label: "Mei", storyline: "s1", metadata: { mood: "wary" } },
    { id: "st1", type: "Setting", label: "Blackwood Tavern", storyline: "s1", metadata: {} },
  ],
  edges: [{ source: "c1", target: "st1", type: "present_at", metadata: { visibility: "public" } }],
});

describe("GraphView", () => {
  beforeEach(() => {
    getScenarioGraph.mockReset();
  });

  it("stays silent for a graph that arrives quickly", async () => {
    let resolve!: (g: ScenarioGraph) => void;
    getScenarioGraph.mockReturnValue(new Promise<ScenarioGraph>((r) => (resolve = r)));
    render(<GraphView scenarioId="sc1" />);

    // A warm graph returns well inside the 300ms gate, so the status line must
    // never appear — it would be pure flicker between the click and the canvas.
    expect(screen.queryByText(/reading the story graph/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Story graph")).toHaveAttribute("aria-busy", "true");

    resolve(POPULATED);
    expect(await screen.findByTestId("graph-canvas")).toBeInTheDocument();
  });

  it("shows the loading line once the wait becomes perceptible", async () => {
    getScenarioGraph.mockReturnValue(new Promise<ScenarioGraph>(() => {}));
    render(<GraphView scenarioId="sc1" />);
    expect(
      await screen.findByText(/reading the story graph/i, undefined, { timeout: 2000 }),
    ).toBeInTheDocument();
  });

  it("renders the canvas, the inspector breakdown, and an accessible table when populated", async () => {
    getScenarioGraph.mockResolvedValue(POPULATED);
    render(<GraphView scenarioId="sc1" />);

    expect(await screen.findByTestId("graph-canvas")).toHaveTextContent("canvas:2:1");

    // The inspector overview labels every type (color is never the only signal).
    const inspector = within(screen.getByTestId("graph-inspector"));
    expect(inspector.getByText("Character")).toBeInTheDocument();
    expect(inspector.getByText("Setting")).toBeInTheDocument();
    expect(inspector.getByText("present_at")).toBeInTheDocument();

    // Accessible tables list nodes and name-resolved edges.
    const nodeTable = screen.getByRole("table", { name: /story-graph nodes/i });
    expect(nodeTable).toHaveTextContent("Mei");
    const edgeTable = screen.getByRole("table", { name: /story-graph connections/i });
    expect(edgeTable).toHaveTextContent("present_at");

    expect(screen.getByRole("img", { name: /story graph with 2 nodes and 1 connection/i })).toBeInTheDocument();
  });

  it("selecting a node shows its properties and marks it selected on the canvas", async () => {
    getScenarioGraph.mockResolvedValue(POPULATED);
    render(<GraphView scenarioId="sc1" />);
    await screen.findByTestId("graph-canvas");

    await userEvent.click(screen.getByRole("button", { name: "select-node" }));

    const inspector = within(screen.getByTestId("graph-inspector"));
    expect(inspector.getByRole("heading", { name: "Mei" })).toBeInTheDocument();
    expect(inspector.getByText(/id: c1/i)).toBeInTheDocument();
    expect(inspector.getByText("mood")).toBeInTheDocument();
    expect(inspector.getByText("wary")).toBeInTheDocument();
    // Selection propagates back to the canvas for highlighting.
    expect(screen.getByTestId("graph-canvas")).toHaveAttribute("data-selected-node", "c1");

    // Back returns to the overview.
    await userEvent.click(inspector.getByRole("button", { name: /overview/i }));
    expect(within(screen.getByTestId("graph-inspector")).getByText(/node types/i)).toBeInTheDocument();
  });

  it("selecting an edge shows its properties and marks it selected on the canvas", async () => {
    getScenarioGraph.mockResolvedValue(POPULATED);
    render(<GraphView scenarioId="sc1" />);
    await screen.findByTestId("graph-canvas");

    await userEvent.click(screen.getByRole("button", { name: "select-edge" }));

    const inspector = within(screen.getByTestId("graph-inspector"));
    expect(inspector.getByText("present_at")).toBeInTheDocument();
    expect(inspector.getByText("visibility")).toBeInTheDocument();
    expect(screen.getByTestId("graph-canvas")).toHaveAttribute("data-selected-edge", "c1|st1|present_at");

    // Clicking the background clears back to the overview.
    await userEvent.click(screen.getByRole("button", { name: "bg-click" }));
    expect(within(screen.getByTestId("graph-inspector")).getByText(/node types/i)).toBeInTheDocument();
  });

  it("shows a calm offline state when the graph is unavailable", async () => {
    getScenarioGraph.mockResolvedValue(graph({ available: false }));
    render(<GraphView scenarioId="sc1" />);
    expect(await screen.findByText(/story graph is offline/i)).toBeInTheDocument();
    expect(screen.queryByTestId("graph-canvas")).not.toBeInTheDocument();
  });

  it("shows an empty state when available but with no nodes", async () => {
    getScenarioGraph.mockResolvedValue(graph({ available: true, nodes: [], edges: [] }));
    render(<GraphView scenarioId="sc1" />);
    expect(await screen.findByText(/graph is empty/i)).toBeInTheDocument();
    expect(screen.queryByTestId("graph-canvas")).not.toBeInTheDocument();
  });

  it("shows an error with a retry that refetches", async () => {
    getScenarioGraph.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(POPULATED);
    render(<GraphView scenarioId="sc1" />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be loaded/i);

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByTestId("graph-canvas")).toBeInTheDocument();
    expect(getScenarioGraph).toHaveBeenCalledTimes(2);
  });
});
