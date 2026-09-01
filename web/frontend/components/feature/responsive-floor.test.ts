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
  it("puts one 44px target below sm, not five", () => {
    const src = readFileSync("components/feature/BeatControls.tsx", "utf8");
    // Below `sm` the cluster IS the `⋯` trigger, and it holds the repo's 44px touch floor.
    // Five of them, permanently visible because touch has no hover, was 220px of chrome on
    // every beat of the transcript.
    expect(src).toContain('aria-haspopup="menu"');
    expect(src).toContain('h-[44px] w-[44px]');
    // …and every row the menu opens onto is a touch target in its own right.
    expect(src).toContain('min-h-[44px]');
  });

  it("keeps the wide toolbar above WCAG 2.5.8's 24px", () => {
    const src = readFileSync("components/feature/BeatControls.tsx", "utf8");
    expect(src).toContain("h-[26px] w-[26px]");
  });

  it("never hides the cluster outright — a hidden control is out of the tab order", () => {
    const src = readFileSync("components/feature/BeatControls.tsx", "utf8");
    expect(src).not.toContain("hidden sm:flex");
    // The hover reveal lives on the BAR that holds the cluster, not on the cluster: quiet at
    // sm+ via opacity, plainly visible below it, where there is no pointer to hover with.
    const view = readFileSync("features/story-player/StoryPlayerView.tsx", "utf8");
    expect(view).toContain("sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100");
  });

  it("gives the take pager the same floor", () => {
    const src = readFileSync("components/feature/BeatTakePager.tsx", "utf8");
    expect(src).toContain("h-[44px] w-[44px]");
    expect(src).toContain("sm:h-[26px] sm:w-[26px]");
  });
});

describe("sr-only cannot grow the root scroller", () => {
  /**
   * The one defect in this area that silently invalidates every other responsive
   * measurement. Tailwind's stock `sr-only` is `position: absolute`; with no positioned
   * ancestor it lays out against the *initial containing block*, escapes every
   * `overflow: hidden` between it and the root, and adds its offset to the ROOT scroller.
   * Measured 2026-08-11: `TriagePanel`'s per-row labels grew the document to **6212px** for
   * 28 files in a 720px viewport.
   *
   * jsdom performs **no layout**, so the symptom itself cannot be reproduced here. This is
   * the source guard; `utils/scripts/check_frontend_css.mjs` asserts the *compiled* value
   * (the winning rule, since both land in `@layer utilities`); and the live measurement —
   * `documentElement.scrollHeight === clientHeight` with a real document list — belongs to
   * the acceptance pass.
   */
  it("overrides the utility in globals.css rather than patching each call site", () => {
    const css = readFileSync("app/globals.css", "utf8");
    const block = /(?:^|\n)\.sr-only\s*\{([^}]*)\}/.exec(css)?.[1];
    expect(block, "no unlayered `.sr-only` rule in globals.css").toBeTruthy();
    expect(block).toMatch(/position:\s*fixed/);
  });

  it("uses a bare rule, not @utility — the two pipelines merge that differently", () => {
    // `@utility sr-only` does not shadow the core utility, it MERGES with it, and the
    // offline PostCSS run and Turbopack order the merge differently. That form passed the
    // CSS gate while the browser was still served `position: absolute`.
    // Comments explain the trap by name, so strip them before scanning — the same reason
    // `stripComments` exists for the other guards in this file.
    const css = stripComments(readFileSync("app/globals.css", "utf8"));
    expect(css).not.toMatch(/@utility\s+sr-only\b/);
  });

  it("fails if anyone adopts not-sr-only, whose escape hatch this override breaks", () => {
    // `not-sr-only` sets `position: static` from inside `@layer utilities` and loses to the
    // unlayered override. A `:not(.not-sr-only)` guard was tried; the compiler folds it away.
    // Nothing uses it today, so the cost is zero — but the day something does, it will fail
    // silently, and this is the tripwire.
    const users: string[] = [];
    for (const { path, text } of sourceFiles()) {
      if (/\bnot-sr-only\b/.test(text)) users.push(path);
    }
    expect(users).toEqual([]);
  });

  it("no call site fights the override with its own positioning utilities", () => {
    // An `sr-only` element that is also given `absolute`/`inset-*` would reintroduce the
    // bug one component at a time.
    const offenders: string[] = [];
    for (const { path, text } of sourceFiles()) {
      for (const match of text.matchAll(/className="[^"]*\bsr-only\b[^"]*"/g)) {
        if (/\b(absolute|inset-|top-\[|left-\[)/.test(match[0])) {
          const line = text.slice(0, match.index).split("\n").length;
          offenders.push(`${path}:${line} ${match[0]}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
