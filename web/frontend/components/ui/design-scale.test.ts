import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

/**
 * Guards on the design scales.
 *
 * The 2026-08-31 baseline audit (docs/audit/audit-report.md) measured the
 * mechanism behind "every part looks good, the whole looks unpolished":
 * 625 arbitrary font sizes over 30 distinct values and 1,335 arbitrary spacing
 * values over 165, across 136 component files, while only 29 of those files
 * used the type tokens the project already shipped. Components tuned in
 * isolation cannot align with each other, because there is nothing to align to.
 *
 * Two kinds of guard live here.
 *
 *  - HARD guards, which express a rule that must always hold. The form-control
 *    floor is one: it is a platform fact, not a preference.
 *  - A RATCHET, which does not claim the codebase is clean — it claims it is
 *    getting cleaner. The budgets below are the counts at the end of the last
 *    completed phase of docs/plans/website-overhaul.md. Each surface rebuild
 *    lowers them. They may never rise.
 *
 * A ratchet is used rather than a zero-tolerance rule because the cleanup spans
 * several phases; a rule that fails until the very last phase is a rule nobody
 * can run in the meantime.
 */

const ROOTS = ["components", "features", "app"];

/** Blank comments in place, so line numbers survive and docs aren't flagged. */
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
      if (statSync(full).isDirectory()) walk(full);
      else if (entry.endsWith(".tsx") && !entry.endsWith(".test.tsx")) {
        out.push({ path: full, text: stripComments(readFileSync(full, "utf8")) });
      }
    }
  };
  for (const root of ROOTS) walk(root);
  return out;
}

const ARBITRARY_TEXT = /text-\[([0-9.]+)px\]/g;
const ARBITRARY_SPACE =
  /\b-?[pm][xytblr]?-\[([0-9.]+)px\]|\bgap(?:-[xy])?-\[([0-9.]+)px\]/g;
const ARBITRARY_RADIUS = /rounded(?:-[a-z]+)?-\[([0-9.]+)px\]/g;

function countAll(pattern: RegExp): number {
  let total = 0;
  for (const { text } of sourceFiles()) {
    total += [...text.matchAll(new RegExp(pattern.source, "g"))].length;
  }
  return total;
}

describe("the form-control floor", () => {
  /**
   * iOS Safari zooms the page when an input/select/textarea renders below
   * 16 CSS px on focus, and does not reliably zoom back out. The baseline audit
   * measured 776 controls below the floor across seven routes.
   *
   * The only correct font utilities on a form control are `text-field` (pinned
   * >= 16px in every size preset, Compact included) and `text-body` (16px at
   * Default). Every token below those — `text-ui`, `text-label`, `text-tag`,
   * `text-eyebrow`, `text-body-sm` — is under the floor by design, so wearing
   * one on a control is the bug this catches.
   *
   * Disabling zoom is NOT the alternative fix; that is a WCAG 1.4.4 failure.
   */
  const CONTROL = /<(input|textarea|select)\b/g;
  const UNDER_FLOOR_TOKEN = /\btext-(ui|label|tag|eyebrow|body-sm)\b/;

  /**
   * The end of the control's OWN opening tag.
   *
   * A fixed-size window around `<input` is not good enough and was tried first:
   * it reads a `text-label` on the *sibling* `<span>` that labels the field, or
   * on the pill wrapping a visually-hidden radio, and reports 30 offenders
   * against a rendered page that has none. Braces and string literals are
   * tracked so a `className={cn(...)}` containing `>` does not end the tag early.
   */
  function tagEnd(src: string, start: number): number | null {
    let depth = 0;
    let quote: string | null = null;
    for (let i = start; i < src.length; i++) {
      const ch = src[i];
      if (quote) {
        if (ch === quote && src[i - 1] !== "\\") quote = null;
      } else if (ch === '"' || ch === "'" || ch === "`") quote = ch;
      else if (ch === "{") depth++;
      else if (ch === "}") depth--;
      else if (ch === ">" && depth === 0 && i > start) return i;
    }
    return null;
  }

  /**
   * Resolve `className={SOME_CONST}` against module-level string constants, so a
   * shared control class (StatsEditor's `TXT`, VoiceSamplesEditor's input class)
   * is checked rather than skipped.
   */
  function constants(text: string): Map<string, string> {
    const out = new Map<string, string>();
    for (const m of text.matchAll(
      /(?:const|let)\s+([A-Za-z_$][\w$]*)\s*(?::\s*string\s*)?=\s*("(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`)/g,
    )) {
      out.set(m[1], m[2]);
    }
    return out;
  }

  function controlOffenders(): string[] {
    const offenders: string[] = [];
    for (const { path, text } of sourceFiles()) {
      const consts = constants(text);
      for (const match of text.matchAll(CONTROL)) {
        const end = tagEnd(text, match.index!);
        if (end === null) continue;
        let tag = text.slice(match.index!, end);
        // Inline whatever module constants this tag references.
        for (const [name, value] of consts) {
          if (new RegExp(`\\{\\s*${name}\\s*\\}|\\b${name}\\b`).test(tag)) {
            tag += " " + value;
          }
        }
        const line = text.slice(0, match.index!).split("\n").length;
        const arbitrary = [...tag.matchAll(ARBITRARY_TEXT)].find(
          (m) => Number.parseFloat(m[1]) < 16,
        );
        if (arbitrary) {
          offenders.push(`${path}:${line} <${match[1]}> ${arbitrary[0]}`);
          continue;
        }
        const token = tag.match(UNDER_FLOOR_TOKEN);
        if (token) offenders.push(`${path}:${line} <${match[1]}> ${token[0]}`);
      }
    }
    return offenders;
  }

  it("is declared in themes.css and pinned >= 16px in every size preset", () => {
    const css = readFileSync("styles/themes.css", "utf8");
    const presets = [...css.matchAll(/--fs-field:\s*([0-9.]+)px/g)].map((m) =>
      Number.parseFloat(m[1]),
    );
    // :root + the four .fs-* presets.
    expect(presets).toHaveLength(5);
    for (const size of presets) expect(size).toBeGreaterThanOrEqual(16);
  });

  it("is the base font-size for every unstyled control", () => {
    const css = readFileSync("app/globals.css", "utf8");
    // In @layer base, so a component that genuinely wants larger still wins.
    expect(css).toMatch(
      /@layer base \{[\s\S]*?input,\s*select,\s*textarea \{\s*font-size: var\(--fs-field\);/,
    );
  });

  it("is respected by every form control", () => {
    // Started at 43. Verified in the browser as well as in source: every
    // input/select/textarea on all seven sampled routes computes >= 16px.
    expect(controlOffenders()).toEqual([]);
  });
});

describe("the scales are the only source of type, space and radius", () => {
  /**
   * These started as a ratchet — budgets of 623 / 1293 / 228, lowered per phase.
   * The surface rebuild took all three to zero, so the ratchet became a rule.
   *
   * A component that needs a value not on a scale means the SCALE gains a step,
   * in themes.css, once — not that the component gains a number. Width, height,
   * inset and position are deliberately NOT covered: those are layout facts
   * rather than rhythm, and forcing them onto a nine-step scale would be worse
   * than leaving them arbitrary.
   */
  it("uses no arbitrary font size", () => {
    expect(countAll(ARBITRARY_TEXT)).toBe(0);
  });

  it("uses no arbitrary spacing value", () => {
    expect(countAll(ARBITRARY_SPACE)).toBe(0);
  });

  it("uses no arbitrary border radius", () => {
    expect(countAll(ARBITRARY_RADIUS)).toBe(0);
  });
});

describe("the scales exist and are mapped", () => {
  it("declares space, radius and elevation steps in themes.css", () => {
    const css = readFileSync("styles/themes.css", "utf8");
    for (const token of [
      "--sp-3xs", "--sp-2xs", "--sp-xs", "--sp-sm", "--sp-md",
      "--sp-lg", "--sp-xl", "--sp-2xl", "--sp-3xl",
      "--r-xs", "--r-sm", "--r-md", "--r-lg",
      "--elev-sm", "--elev-md", "--elev-lg", "--elev-xl",
    ]) {
      expect(css).toContain(`${token}:`);
    }
  });

  it("declares --header-h, which globals.css already depended on", () => {
    // It was referenced by the scroll-margin rule and declared nowhere, so the
    // 4.5rem fallback always applied while the real bars were 52px and 50px.
    const themes = readFileSync("styles/themes.css", "utf8");
    const globals = readFileSync("app/globals.css", "utf8");
    expect(themes).toMatch(/--header-h:\s*\d+px/);
    expect(globals).toContain("scroll-margin-block-start: var(--header-h)");
    expect(globals).toContain("scroll-padding-top:");
  });

  it("names elevation --elev-* so the Tailwind mapping is not self-referential", () => {
    // `--shadow-sm: var(--shadow-sm)` inside `@theme inline` compiles to a
    // custom property that refers to itself — the same collision the --ease-*
    // note in globals.css documents.
    const themes = readFileSync("styles/themes.css", "utf8");
    expect(themes).not.toMatch(/^\s*--shadow-(sm|md|lg|xl):/m);
  });

  it("gives every theme a color-scheme, so native UI follows the theme", () => {
    const css = readFileSync("styles/themes.css", "utf8");
    const blocks = [...css.matchAll(/\.(theme-[a-z]+)\s*\{([\s\S]*?)\n\}/g)];
    expect(blocks).toHaveLength(3);
    for (const [, name, body] of blocks) {
      expect(body, `${name} declares color-scheme`).toMatch(/color-scheme:\s*(light|dark)/);
    }
  });

  it("derives entity colour from the theme ink rather than using it raw", () => {
    // Raw entity colours as text produced 71 contrast failures; the recipe and
    // its two ratios are gated by utils/scripts/check_contrast.py.
    const css = readFileSync("styles/themes.css", "utf8");
    expect(css).toMatch(
      /--entity-ink:\s*color-mix\(in oklab, var\(--entity\) \d+%, var\(--ink\)\)/,
    );
    expect(css).toMatch(
      /--entity-ink-strong:\s*color-mix\(in oklab, var\(--entity\) \d+%, var\(--ink\)\)/,
    );
  });
});
