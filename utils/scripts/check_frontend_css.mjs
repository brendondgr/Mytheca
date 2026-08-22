#!/usr/bin/env node
/**
 * Compile web/frontend/app/globals.css through the real Tailwind v4 pipeline
 * and fail on anything that would break at build time.
 *
 * Why this exists: `next build` is the normal gate for the stylesheet, but it
 * cannot run in a sandbox without network access — `next/font/google` fetches
 * Cinzel / EB Garamond / IBM Plex Mono at build time and hard-fails offline.
 * That left the frontend with no way at all to check that globals.css,
 * themes.css, and motion.css still compile. This script is that check: it runs
 * PostCSS + @tailwindcss/postcss over the same entry point Next uses, with no
 * network involved.
 *
 * It also asserts three things the compiler itself will not complain about:
 *   - No custom property is defined in terms of itself. `@theme inline` with a
 *     key that collides with a token name (e.g. `--ease-out: var(--ease-out)`)
 *     silently emits a self-referential declaration; it may still resolve via
 *     an unlayered redefinition, but only by accident of cascade order.
 *   - Every `var(--dur-*)` / `var(--ease-*)` / `var(--lift-*)` motion token
 *     referenced anywhere actually has a definition.
 *   - An UNLAYERED `.sr-only` rule declaring `position: fixed` survives
 *     compilation. Tailwind's stock utility is `absolute`, which escapes every
 *     `overflow: hidden` between it and the root and inflates the ROOT scroller
 *     — measured at 6212px of blank page for 28 files in a 720px viewport.
 *     "Unlayered" is the load-bearing half: an override inside
 *     `@layer utilities` wins only on source order, and this script's pipeline
 *     and Turbopack order them differently. An earlier `@utility sr-only` form
 *     produced two rules here (ours last, so it looked fine) and ONE merged
 *     rule in the browser that still said `absolute`. A gate that passes on a
 *     broken app is worse than no gate.
 *
 * Usage:  node utils/scripts/check_frontend_css.mjs
 * Exit:   0 = clean, 1 = a problem worth failing a build over.
 */

import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const frontend = path.join(repoRoot, "web", "frontend");
const entry = path.join(frontend, "app", "globals.css");

// Resolve postcss + the Tailwind plugin out of web/frontend/node_modules, so the
// script can be run from the repo root without its own dependency tree.
const require = createRequire(path.join(frontend, "package.json"));

let postcss, tailwind, source;
try {
  postcss = require("postcss");
  tailwind = require("@tailwindcss/postcss");
  source = require("node:fs").readFileSync(entry, "utf8");
} catch (err) {
  console.error(`✗ could not load the frontend CSS toolchain: ${err.message}`);
  console.error("  Run `npm install` in web/frontend first.");
  process.exit(1);
}

const plugin = tailwind.default ?? tailwind;
let css;
try {
  const result = await postcss([plugin({ base: frontend })]).process(source, { from: entry });
  css = result.css;
  for (const warning of result.warnings()) {
    console.error(`✗ ${warning.toString()}`);
  }
  if (result.warnings().length > 0) process.exit(1);
} catch (err) {
  console.error(`✗ globals.css failed to compile:\n${err.message}`);
  process.exit(1);
}

/**
 * Remove the body of every `@layer name { … }` block, leaving only unlayered CSS.
 * Brace-counted rather than regexed, because layer bodies nest (`@media`, `@supports`).
 */
function stripLayerBlocks(text) {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const at = text.startsWith("@layer", i);
    if (!at) {
      out += text[i];
      continue;
    }
    const brace = text.indexOf("{", i);
    const semi = text.indexOf(";", i);
    // `@layer a, b;` is a declaration, not a block — keep skipping past it either way.
    if (brace === -1 || (semi !== -1 && semi < brace)) {
      i = semi === -1 ? text.length : semi;
      continue;
    }
    let depth = 0;
    let j = brace;
    for (; j < text.length; j++) {
      if (text[j] === "{") depth++;
      else if (text[j] === "}" && --depth === 0) break;
    }
    i = j;
  }
  return out;
}

const problems = [];

// 1. Self-referential custom properties.
for (const match of css.matchAll(/--([\w-]+):\s*var\(\s*--([\w-]+)\s*\)/g)) {
  if (match[1] === match[2]) {
    problems.push(`--${match[1]} is defined as var(--${match[1]}) — a self-referential custom property.`);
  }
}

// 2. Motion tokens referenced but never defined.
const defined = new Set([...css.matchAll(/--([\w-]+)\s*:/g)].map((m) => m[1]));
const referenced = new Set(
  [...css.matchAll(/var\(\s*--((?:dur|ease|lift|stagger)-[\w-]+)/g)].map((m) => m[1]),
);
for (const token of referenced) {
  if (!defined.has(token)) problems.push(`var(--${token}) is referenced but never defined.`);
}

// 3. An unlayered `.sr-only` override must survive compilation — see the block comment in
// globals.css. Strip every `@layer { … }` body first: what is left is unlayered CSS, which
// beats any layer regardless of source order. Checking only that *some* rule says `fixed`
// would pass for an override that the cascade discards.
const unlayered = stripLayerBlocks(css);
const srOnly = /\.sr-only(?::not\([^)]*\))?\s*\{([^}]*)\}/.exec(unlayered);
if (!srOnly) {
  problems.push(
    "No unlayered `.sr-only` rule in the compiled stylesheet. Tailwind's own is " +
      "`position: absolute` and inflates the root scroller; the override must be unlayered " +
      "to beat it by layer precedence rather than by source order. See app/globals.css.",
  );
} else if (!/position:\s*fixed/.test(srOnly[1])) {
  problems.push(
    `The unlayered .sr-only rule does not declare position: fixed (found: ${
      /position:\s*([\w-]+)/.exec(srOnly[1])?.[1] ?? "no position"
    }). See app/globals.css.`,
  );
}

if (problems.length > 0) {
  for (const problem of problems) console.error(`✗ ${problem}`);
  process.exit(1);
}

console.log(
  `✓ frontend CSS compiles (${(css.length / 1024).toFixed(1)} KB), ` +
    `${referenced.size} motion tokens resolved, no self-referential properties, ` +
    `sr-only is unlayered and position: fixed.`,
);
