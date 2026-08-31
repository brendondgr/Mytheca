import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

/**
 * Exactly one AppShell per page.
 *
 * `app/layout.tsx` wraps every route in one. Two feature views ALSO rendered
 * their own, so `/options` and `/storylines/[id]/documents` mounted two nested
 * `.mytheca-themed` grounds, two MotionProviders and two ToastProviders.
 *
 * That was invisible until the shell gained a skip link — and then the first
 * Tab and the second Tab both landed on "Skip to content", measured in the
 * browser. A duplicated landmark or bypass link is worse than a missing one:
 * it teaches a keyboard user the control does not work.
 */
/**
 * Blank comments in place, so a guard cannot flag its own documentation — the
 * note in each de-nested view explaining why there is no `<AppShell>` here
 * reads, to a regex, exactly like the offence it describes.
 */
function code(path: string): string {
  return readFileSync(path, "utf8").replace(
    /\/\*[\s\S]*?\*\/|\/\/[^\n]*|\{\/\*[\s\S]*?\*\/\}/g,
    (m) => m.replace(/[^\n]/g, " "),
  );
}

function viewFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry.endsWith(".tsx") && !entry.endsWith(".test.tsx")) out.push(full);
    }
  };
  walk("features");
  walk("components");
  return out;
}

describe("the app shell is mounted once", () => {
  it("is rendered by the root layout", () => {
    expect(readFileSync("app/layout.tsx", "utf8")).toContain("<AppShell>");
  });

  it("is not rendered again by any feature view", () => {
    const offenders = viewFiles().filter((f) => code(f).includes("<AppShell"));
    expect(offenders).toEqual([]);
  });

  it("carries exactly one skip link, in the shell", () => {
    const shell = readFileSync("components/layout/AppShell.tsx", "utf8");
    expect(shell).toContain("<SkipLink />");
    const elsewhere = viewFiles().filter(
      (f) =>
        !f.endsWith("AppShell.tsx") &&
        !f.endsWith("SkipLink.tsx") &&
        code(f).includes("<SkipLink"),
    );
    expect(elsewhere).toEqual([]);
  });
});

describe("single-key shortcuts are gated (WCAG 2.1.4)", () => {
  const src = readFileSync("hooks/use-scene-shortcuts.ts", "utf8");

  it("never fires a bare letter shortcut while the player is typing", () => {
    // `/` and `?` must sit AFTER the `if (editable) return` guard, or they fire
    // mid-sentence and mid-dictation.
    const guard = src.indexOf("if (editable) return");
    expect(guard).toBeGreaterThan(-1);
    expect(src.indexOf('e.key === "/"')).toBeGreaterThan(guard);
    expect(src.indexOf('e.key === "?"')).toBeGreaterThan(guard);
  });

  it("never shadows a browser shortcut", () => {
    expect(src).toMatch(/if \(e\.metaKey \|\| e\.ctrlKey \|\| e\.altKey\) return/);
  });
});
