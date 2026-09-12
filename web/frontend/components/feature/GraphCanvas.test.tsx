import { describe, expect, it } from "vitest";
import { edgeKey, shortLabel } from "@/components/feature/GraphCanvas";

// The canvas itself needs a real 2D context and a force simulation, so what is unit-tested
// here is the pure logic it draws with. The rest is covered through `GraphView`.

describe("edgeKey", () => {
  it("separates two edges of different types between the same pair", () => {
    const a = edgeKey({ source: "mei", target: "beth", type: "trusts" });
    const b = edgeKey({ source: "mei", target: "beth", type: "fears" });
    expect(a).not.toBe(b);
  });

  it("separates the two directions of one relationship", () => {
    expect(edgeKey({ source: "mei", target: "beth", type: "trusts" })).not.toBe(
      edgeKey({ source: "beth", target: "mei", type: "trusts" }),
    );
  });
});

describe("shortLabel", () => {
  it("leaves a name alone", () => {
    expect(shortLabel("Maerin Voss")).toBe("Maerin Voss");
    expect(shortLabel("The Saltworn Tavern")).toBe("The Saltworn Tavern");
  });

  it("truncates a sentence-length label, which Event and Secret nodes carry", () => {
    const label = shortLabel("The drowned ledger names every salt buyer in the upper town");
    expect(label).toHaveLength(30);
    expect(label.endsWith("…")).toBe(true);
  });

  it("does not leave a dangling space before the ellipsis", () => {
    expect(shortLabel("Aldous set the chapel fire himself")).not.toContain(" …");
  });

  it("keeps a label of exactly the limit whole", () => {
    const exact = "x".repeat(30);
    expect(shortLabel(exact)).toBe(exact);
  });
});
