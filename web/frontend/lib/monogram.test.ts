import { describe, it, expect } from "vitest";
import { monoOf } from "@/lib/monogram";

describe("monoOf", () => {
  it("uses the first letters of the first two words", () => {
    expect(monoOf("Maerin Voss")).toBe("MV");
    expect(monoOf("Captain Doran Hale")).toBe("CD");
  });

  it("uses the first two letters of a single word", () => {
    expect(monoOf("Grimm")).toBe("GR");
    expect(monoOf("Pip")).toBe("PI");
  });

  it("falls back to ? for empty input", () => {
    expect(monoOf("")).toBe("?");
    expect(monoOf("   ")).toBe("?");
  });
});
