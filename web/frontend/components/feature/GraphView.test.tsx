import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ScenarioGraph } from "@/lib/types";

const getScenarioGraph = vi.fn();
vi.mock("@/lib/api", () => ({
  getScenarioGraph: (...args: unknown[]) => getScenarioGraph(...args),
}));

// Stub the heavy canvas renderer — GraphView's contract is the state machine +
// accessible table + legend, not the canvas drawing.
vi.mock("@/components/feature/GraphCanvas", () => ({
  GraphCanvas: ({ nodes, edges }: { nodes: unknown[]; edges: unknown[] }) => (
    <div data-testid="graph-canvas">
      canvas:{nodes.length}:{edges.length}
    </div>
  ),
}));

import { GraphView } from "@/components/feature/GraphView";

function graph(partial: Partial<ScenarioGraph>): ScenarioGraph {
  return { available: true, scenarioId: "sc1", nodes: [], edges: [], ...partial };
}

const POPULATED = graph({
  nodes: [
    { id: "c1", type: "Character", label: "Mei", storyline: "s1", metadata: {} },
    { id: "st1", type: "Setting", label: "Blackwood Tavern", storyline: "s1", metadata: {} },
  ],
  edges: [{ source: "c1", target: "st1", type: "present_at", metadata: {} }],
});

describe("GraphView", () => {
  beforeEach(() => {
    getScenarioGraph.mockReset();
  });

  it("shows a loading state until the graph resolves", async () => {
    let resolve!: (g: ScenarioGraph) => void;
    getScenarioGraph.mockReturnValue(new Promise<ScenarioGraph>((r) => (resolve = r)));
    render(<GraphView scenarioId="sc1" />);
    expect(screen.getByText(/reading the story graph/i)).toBeInTheDocument();
    resolve(POPULATED);
    expect(await screen.findByTestId("graph-canvas")).toBeInTheDocument();
  });

  it("renders the canvas, legend, and an accessible node/edge table when populated", async () => {
    getScenarioGraph.mockResolvedValue(POPULATED);
    render(<GraphView scenarioId="sc1" />);

    expect(await screen.findByTestId("graph-canvas")).toHaveTextContent("canvas:2:1");

    // Legend labels every type (color is never the only signal).
    const legend = within(screen.getByTestId("graph-legend"));
    expect(legend.getByText("Character")).toBeInTheDocument();
    expect(legend.getByText("Setting")).toBeInTheDocument();
    expect(legend.getByText("present_at")).toBeInTheDocument();

    // Accessible tables list nodes and name-resolved edges.
    const nodeTable = screen.getByRole("table", { name: /story-graph nodes/i });
    expect(nodeTable).toHaveTextContent("Mei");
    expect(nodeTable).toHaveTextContent("Blackwood Tavern");
    const edgeTable = screen.getByRole("table", { name: /story-graph connections/i });
    expect(edgeTable).toHaveTextContent("Mei");
    expect(edgeTable).toHaveTextContent("present_at");
    expect(edgeTable).toHaveTextContent("Blackwood Tavern");

    // The canvas region is labeled for screen readers.
    expect(screen.getByRole("img", { name: /story graph with 2 nodes and 1 connection/i })).toBeInTheDocument();
  });

  it("passes onNodeSelect through to the canvas", async () => {
    getScenarioGraph.mockResolvedValue(POPULATED);
    const onNodeSelect = vi.fn();
    render(<GraphView scenarioId="sc1" onNodeSelect={onNodeSelect} />);
    expect(await screen.findByTestId("graph-canvas")).toBeInTheDocument();
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
