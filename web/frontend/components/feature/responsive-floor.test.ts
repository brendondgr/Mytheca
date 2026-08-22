import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

/**
 * Static guards on the responsive floor.
 *
 * These are source scans, not render tests, and that is deliberate: jsdom does
 * no layout, so it cannot tell you whether something overflows at 320px. What
 * it CAN do is stop the two mistakes that reliably produce that overflow from
 * being reintroduced — and both were present in this codebase before the
 * frontend-polish pass.
 */

const ROOTS = ["components", "features", "app"];

/**
 * Blank out comments while preserving every byte's position, so line numbers in
 * a failure still point at the real line.
 *
 * Without this the guards flag their own documentation: a comment explaining
 * *why* `hover:scale-110` is forbidden reads, to a regex, exactly like the
 * offence it describes.
 */
function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, (match) =>
    match.replace(/[^\n]/g, " "),
  );
}

function sourceFiles(): { path: string; text: string }[] {
  const out: { path: string; text: string }[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) {
        walk(full);
      } else if (entry.endsWith(".tsx") && !entry.endsWith(".test.tsx")) {
        out.push({ path: full, text: stripComments(readFileSync(full, "utf8")) });
      }
    }
  };
  for (const root of ROOTS) walk(root);
  return out;
}

describe("responsive floor", () => {
  it("uses dvh, never vh, for viewport-relative sizing", () => {
    // `vh` measures the viewport as if mobile browser chrome were hidden, so a
    // `max-h-[90vh]` panel can be taller than the space actually on screen —
    // the classic "the buttons are under the address bar" bug.
    const offenders: string[] = [];
    for (const { path, text } of sourceFiles()) {
      for (const match of text.matchAll(/\[[^\]]*?\d+vh[^\]]*?\]/g)) {
        if (!match[0].includes("dvh")) offenders.push(`${path}: ${match[0]}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("never pins a width at or above 320px without a breakpoint or a cap", () => {
    // A bare `w-[340px]` cannot fit the 320px floor. It is only safe when a
    // responsive prefix or an `lg:`-gated ancestor keeps it off small screens,
    // or when it is a max-/min- constraint rather than a fixed width.
    const offenders: string[] = [];
    for (const { path, text } of sourceFiles()) {
      for (const match of text.matchAll(/(^|\s|")(w-\[(\d+)px\])/g)) {
        const px = Number(match[3]);
        if (px < 320) continue;
        const line = text.slice(0, match.index).split("\n").length;
        const context = text.split("\n")[line - 1] ?? "";
        // `sm:w-[…]`, `md:w-[…]` etc. are matched with their prefix attached,
        // so anything reaching here is genuinely unconditional on this element.
        const gated = /\b(sm|md|lg|xl):/.test(context) || context.includes("lg:block");
        if (!gated) offenders.push(`${path}:${line} ${match[2]}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("keeps hover transforms behind the pointer-gated utilities", () => {
    // Tailwind's `hover:` variant is NOT gated by pointer type. A hover that
    // MOVES an element therefore sticks after a tap on touch, leaving the
    // element visibly displaced until the user taps elsewhere. Movement goes
    // through .hover-lift / .close-button-hover, which carry the media query.
    const offenders: string[] = [];
    for (const { path, text } of sourceFiles()) {
      for (const match of text.matchAll(/hover:(scale-|-?translate-)/g)) {
        const line = text.slice(0, match.index).split("\n").length;
        offenders.push(`${path}:${line} ${match[0]}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("beat controls at the 320px floor", () => {
  it("sizes its targets to 44px below sm and 24px above", () => {
    const src = readFileSync("components/feature/BeatControls.tsx", "utf8");
    // WCAG 2.5.8 asks for 24x24; the touch floor this repo holds itself to is 44.
    expect(src).toContain("h-[44px] w-[44px]");
    expect(src).toContain("sm:h-[24px] sm:w-[24px]");
  });

  it("never hides the cluster outright — a hidden control is out of the tab order", () => {
    const src = readFileSync("components/feature/BeatControls.tsx", "utf8");
    expect(src).not.toContain("hidden sm:flex");
    // Quiet at sm+ via opacity, plainly visible below it (touch has no hover).
    expect(src).toContain("sm:opacity-0");
  });

  it("gives the take pager the same floor", () => {
    const src = readFileSync("components/feature/BeatTakePager.tsx", "utf8");
    expect(src).toContain("h-[44px] w-[44px]");
    expect(src).toContain("sm:h-[24px] sm:w-[24px]");
  });
});
