import { describe, expect, it } from "vitest";
import { edgeColor, graphLegend, graphTypeCounts, nodeColor } from "@/lib/graphColors";

const HEX = /^#[0-9a-f]{6}$/i;

describe("graphColors", () => {
  it("gives each built-in node type a distinct, valid hex color", () => {
    const types = ["Character", "Setting", "Event", "Faction", "Secret", "Consequence"];
    const colors = types.map(nodeColor);
    colors.forEach((c) => expect(c).toMatch(HEX));
    expect(new Set(colors).size).toBe(types.length); // all distinct
  });

  it("colors edges by valence family (positive/negative shared within group)", () => {
    expect(edgeColor("loves")).toBe(edgeColor("trusts"));
    expect(edgeColor("fears")).toBe(edgeColor("resents"));
    expect(edgeColor("loves")).not.toBe(edgeColor("fears"));
    expect(edgeColor("present_at")).toMatch(HEX);
  });

  it("assigns unknown types a stable, deterministic color (expandable)", () => {
    // A brand-new entity type gets a valid color, the same one every call.
    const a1 = nodeColor("Artifact");
    const a2 = nodeColor("Artifact");
    expect(a1).toMatch(HEX);
    expect(a1).toBe(a2);
    // Different unknown types get different colors.
    expect(nodeColor("Artifact")).not.toBe(nodeColor("Vehicle"));
    // Node and edge namespaces are separate, so a shared name can differ.
    expect(edgeColor("mentored_by")).toMatch(HEX);
    expect(edgeColor("mentored_by")).toBe(edgeColor("mentored_by"));
  });

  it("falls back to a gray for missing types", () => {
    expect(nodeColor(null)).toMatch(HEX);
    expect(nodeColor(undefined)).toBe(nodeColor(null));
    expect(edgeColor("")).toMatch(HEX);
  });

  it("builds a de-duplicated legend: nodes first, then edges, sorted", () => {
    const legend = graphLegend(
      [{ type: "Setting" }, { type: "Character" }, { type: "Character" }],
      [{ type: "present_at" }, { type: "loves" }, { type: "present_at" }],
    );
    expect(legend.map((l) => `${l.kind}:${l.type}`)).toEqual([
      "node:Character",
      "node:Setting",
      "edge:loves",
      "edge:present_at",
    ]);
    legend.forEach((l) => expect(l.color).toMatch(HEX));
  });

  it("counts types, sorted by count then name, with matching colors", () => {
    const { nodes, edges } = graphTypeCounts(
      [{ type: "Character" }, { type: "Setting" }, { type: "Character" }, { type: "Character" }],
      [{ type: "present_at" }, { type: "knows" }, { type: "present_at" }],
    );
    expect(nodes).toEqual([
      { type: "Character", color: nodeColor("Character"), count: 3 },
      { type: "Setting", color: nodeColor("Setting"), count: 1 },
    ]);
    expect(edges).toEqual([
      { type: "present_at", color: edgeColor("present_at"), count: 2 },
      { type: "knows", color: edgeColor("knows"), count: 1 },
    ]);
  });

  it("folds untyped elements into an 'Untyped' count bucket", () => {
    const { nodes } = graphTypeCounts([{ type: null }, { type: undefined }, { type: "Character" }], []);
    const untyped = nodes.find((n) => n.type === "Untyped");
    expect(untyped?.count).toBe(2);
  });

  it("folds untyped nodes/edges into a single 'Untyped' legend entry", () => {
    const legend = graphLegend(
      [{ type: null }, { type: undefined }, { type: "Character" }],
      [{ type: "" }, { type: null }],
    );
    const untypedNodes = legend.filter((l) => l.kind === "node" && l.type === "Untyped");
    const untypedEdges = legend.filter((l) => l.kind === "edge" && l.type === "Untyped");
    expect(untypedNodes).toHaveLength(1);
    expect(untypedEdges).toHaveLength(1);
  });
});
