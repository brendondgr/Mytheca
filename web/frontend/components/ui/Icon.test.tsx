import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { Icon, ICON_NAMES } from "./Icon";

describe("the icon set", () => {
  it("draws exactly one svg with one path for every name", () => {
    for (const name of ICON_NAMES) {
      const { container, unmount } = render(<Icon name={name} />);
      const svgs = container.querySelectorAll("svg");
      expect(svgs, name).toHaveLength(1);
      // One path per icon is the constraint that keeps the set consistent: a
      // multi-path icon accumulates its own stroke rules and stops matching the
      // others at the same size.
      expect(svgs[0].querySelectorAll("path"), name).toHaveLength(1);
      expect(svgs[0].getAttribute("d")).toBeNull();
      unmount();
    }
  });

  it("is decorative by default and named only when asked", () => {
    // Nearly every icon here sits inside a button that already carries an
    // aria-label. Announcing itself there is a duplicate reading, which is why
    // the default is hidden rather than named.
    const { container } = render(<Icon name="send" />);
    const svg = container.querySelector("svg")!;
    expect(svg.getAttribute("aria-hidden")).toBe("true");
    expect(svg.getAttribute("role")).toBeNull();

    const named = render(<Icon name="send" label="Send" />);
    const namedSvg = named.container.querySelector("svg")!;
    expect(namedSvg.getAttribute("role")).toBe("img");
    expect(namedSvg.getAttribute("aria-label")).toBe("Send");
    expect(namedSvg.getAttribute("aria-hidden")).toBeNull();
  });

  it("inherits colour from its control", () => {
    // A hardcoded stroke turns off hover, focus and aria-pressed for the glyph
    // and strands it on the hover ground.
    const { container } = render(<Icon name="gear" />);
    const svg = container.querySelector("svg")!;
    expect(svg.getAttribute("stroke")).toBe("currentColor");
    expect(svg.getAttribute("fill")).toBe("none");
  });

  it("shares one grid, so two icons at one size have one visual mass", () => {
    const a = render(<Icon name="cast" size={18} />).container.querySelector("svg")!;
    const b = render(<Icon name="plan" size={18} />).container.querySelector("svg")!;
    expect(a.getAttribute("viewBox")).toBe("0 0 24 24");
    expect(b.getAttribute("viewBox")).toBe("0 0 24 24");
    expect(a.getAttribute("stroke-width")).toBe(b.getAttribute("stroke-width"));
    expect(a.getAttribute("width")).toBe("18");
  });
});

/**
 * The rule that keeps the set a set.
 *
 * Eight components drew their own inline `<svg>` before this file existed — fifteen
 * drawings, each on its own grid at its own weight. All fifteen are migrated, so this
 * is a hard rule at zero rather than a ratchet: there is nothing left to count down.
 * The two exemptions below are exempt on a principle, not on a backlog.
 */
describe("inline svg outside the set", () => {
  const ROOTS = ["components", "features", "app"];

  /** Blank comments in place so line numbers survive and prose is not counted. */
  const code = (text: string) =>
    text.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, (m) => m.replace(/[^\n]/g, " "));

  function sources(): { path: string; text: string }[] {
    const out: { path: string; text: string }[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir)) {
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) walk(full);
        else if (entry.endsWith(".tsx") && !entry.endsWith(".test.tsx"))
          out.push({ path: full, text: code(readFileSync(full, "utf8")) });
      }
    };
    for (const root of ROOTS) walk(root);
    return out;
  }

  it("does not exist", () => {
    const offenders: string[] = [];
    for (const { path, text } of sources()) {
      // Icon.tsx is the set itself; the two data visualisations below draw
      // geometry from live values rather than from a fixed path, which is
      // drawing, not iconography.
      if (
        path.endsWith("ui/Icon.tsx") ||
        path.endsWith("ContextUsageDial.tsx") ||
        path.endsWith("GraphCanvas.tsx")
      )
        continue;
      const count = [...text.matchAll(/<svg\b/g)].length;
      if (count) offenders.push(`${path} (${count})`);
    }
    expect(offenders, `use <Icon> instead:\n${offenders.join("\n")}`).toEqual([]);
  });
});
