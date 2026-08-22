import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";

/**
 * The three type families must stay self-hosted.
 *
 * `next/font/google` fetches at BUILD time, so a single reintroduced import makes
 * `next build` hard-fail with no network — which is the root cause every "deferred
 * verification" in docs/checklist.md traced back to. This is a source guard rather than a
 * render test because the failure is a build-time network call, which vitest never performs.
 */
const SOURCE = readFileSync("lib/fonts.ts", "utf8");
const CODE = SOURCE.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, "");

describe("type families are self-hosted", () => {
  it("loads them with next/font/local and never from the network", () => {
    expect(CODE).toContain('from "next/font/local"');
    expect(CODE).not.toContain("next/font/google");
  });

  it("still exports the three CSS variables the stylesheets reference", () => {
    // themes.css and globals.css reference these by name; app/layout.tsx applies the classes.
    for (const variable of ["--font-cinzel", "--font-eb-garamond", "--font-ibm-plex-mono"]) {
      expect(CODE).toContain(`variable: "${variable}"`);
    }
    for (const name of ["export const cinzel", "export const ebGaramond", "export const ibmPlexMono"]) {
      expect(CODE).toContain(name);
    }
  });

  it("keeps swap display and a metric-compatible fallback on every family", () => {
    // Without `adjustFontFallback`/`fallback`, dropping the Google loader would *introduce*
    // the layout shift the Core Web Vitals phase measures.
    expect(CODE.match(/display: "swap"/g)).toHaveLength(3);
    expect(CODE.match(/adjustFontFallback:/g)).toHaveLength(3);
    expect(CODE.match(/fallback: \[/g)).toHaveLength(3);
  });

  it("points at font files that are actually committed", () => {
    const paths = [...CODE.matchAll(/path: "([^"]+)"/g)].map((m) => m[1]);
    expect(paths.length).toBeGreaterThanOrEqual(5);
    for (const rel of paths) {
      // `lib/fonts.ts` resolves `../app/fonts/…` relative to itself.
      expect(() => readFileSync(rel.replace(/^\.\.\//, ""))).not.toThrow();
    }
  });

  it("ships the OFL licence beside each family", () => {
    for (const name of ["Cinzel", "EBGaramond", "IBMPlexMono"]) {
      const licence = readFileSync(`app/fonts/OFL-${name}.txt`, "utf8");
      expect(licence).toContain("SIL Open Font License");
    }
  });
});
