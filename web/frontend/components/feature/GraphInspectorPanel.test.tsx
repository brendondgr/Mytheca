import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { GraphEdge, GraphNode } from "@/lib/types";
import { GraphInspectorPanel } from "@/components/feature/GraphInspectorPanel";

const NODES: GraphNode[] = [
  {
    id: "maerin",
    type: "Character",
    label: "Maerin Voss",
    storyline: "s1",
    metadata: { goal: "Keep the salt routes hidden.", traits: "Patient · Calculating" },
  },
  { id: "aldous", type: "Character", label: "Brother Aldous", storyline: "s1", metadata: {} },
  { id: "wren", type: "Character", label: "Wren Calloway", storyline: "s1", metadata: {} },
  { id: "saltworn", type: "Setting", label: "The Saltworn Tavern", storyline: "s1", metadata: {} },
];
const EDGES: GraphEdge[] = [
  { source: "maerin", target: "saltworn", type: "present_at", metadata: { visibility: "public", weight: 1 } },
  { source: "wren", target: "saltworn", type: "present_at", metadata: {} },
  { source: "maerin", target: "aldous", type: "knows", metadata: {} },
];

describe("GraphInspectorPanel", () => {
  it("shows the node & edge type breakdown with counts when nothing is selected", () => {
    render(<GraphInspectorPanel nodes={NODES} edges={EDGES} selection={null} onClear={vi.fn()} />);

    expect(screen.getByText(/4 nodes · 3 connections/i)).toBeInTheDocument();

    const nodeSection = screen.getByRole("heading", { name: /node types/i }).parentElement!;
    expect(within(nodeSection).getByText("Character")).toBeInTheDocument();
    expect(within(nodeSection).getByText("3")).toBeInTheDocument(); // 3 characters
    expect(within(nodeSection).getByText("Setting")).toBeInTheDocument();

    const edgeSection = screen.getByRole("heading", { name: /edge types/i }).parentElement!;
    expect(within(edgeSection).getByText("present_at")).toBeInTheDocument();
    expect(within(edgeSection).getByText("2")).toBeInTheDocument();
    expect(within(edgeSection).getByText("knows")).toBeInTheDocument();

    expect(screen.getByText(/select a node or edge/i)).toBeInTheDocument();
  });

  it("shows a node's properties when a node is selected, and Back clears it", async () => {
    const onClear = vi.fn();
    render(
      <GraphInspectorPanel
        nodes={NODES}
        edges={EDGES}
        selection={{ kind: "node", node: NODES[0] }}
        onClear={onClear}
      />,
    );
    expect(screen.getByRole("heading", { name: "Maerin Voss" })).toBeInTheDocument();
    expect(screen.getByText("Character")).toBeInTheDocument(); // type badge
    expect(screen.getByText(/id: maerin/i)).toBeInTheDocument();
    // metadata rendered as label + value
    expect(screen.getByText("goal")).toBeInTheDocument();
    expect(screen.getByText(/keep the salt routes hidden/i)).toBeInTheDocument();
    expect(screen.getByText(/patient · calculating/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /overview/i }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("shows a node with no metadata gracefully", () => {
    render(
      <GraphInspectorPanel
        nodes={NODES}
        edges={EDGES}
        selection={{ kind: "node", node: NODES[1] }}
        onClear={vi.fn()}
      />,
    );
    expect(screen.getByText(/no further properties/i)).toBeInTheDocument();
  });

  it("shows an edge's endpoints, type, and properties when an edge is selected", async () => {
    const onClear = vi.fn();
    render(
      <GraphInspectorPanel
        nodes={NODES}
        edges={EDGES}
        selection={{ kind: "edge", edge: EDGES[0] }}
        onClear={onClear}
      />,
    );
    // Name-resolved endpoints
    expect(screen.getByText("Maerin Voss")).toBeInTheDocument();
    expect(screen.getByText("The Saltworn Tavern")).toBeInTheDocument();
    expect(screen.getByText("present_at")).toBeInTheDocument(); // type badge
    // metadata
    expect(screen.getByText("visibility")).toBeInTheDocument();
    expect(screen.getByText("public")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /overview/i }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});
