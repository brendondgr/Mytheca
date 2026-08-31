import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { Page, Section, Stack, Cluster } from "@/components/ui/Page";
import { SkipLink } from "@/components/layout/SkipLink";
import { HeaderBar, HeaderLead, HeaderTrail } from "@/components/layout/HeaderBar";
import { THEME_PAGE_BG, THEME_KEYS, applyThemeClass } from "@/lib/theme";

/**
 * Blank comments in place so a guard cannot flag its own documentation: the
 * prose explaining *why* `userScalable` is forbidden reads, to a regex, exactly
 * like the offence it describes. Positions are preserved so line numbers in a
 * failure still point at the real line.
 */
function code(path: string): string {
  return readFileSync(path, "utf8").replace(
    /\/\*[\s\S]*?\*\/|\/\/[^\n]*/g,
    (match) => match.replace(/[^\n]/g, " "),
  );
}

describe("Page", () => {
  it("is the main landmark, and is the skip link's target", () => {
    render(<Page>content</Page>);
    const main = screen.getByRole("main");
    expect(main).toHaveAttribute("id", "main");
    // Without tabindex="-1" the browser scrolls but does not move focus, so the
    // next Tab restarts at the top of the header — the thing skipping avoids.
    expect(main).toHaveAttribute("tabindex", "-1");
  });

  it("supplies the measure and the fluid gutter, so routes stop inventing them", () => {
    const { container } = render(<Page measure="prose">x</Page>);
    const main = container.querySelector("main")!;
    expect(main.className).toContain("px-gutter");
    expect(main.className).toContain("max-w-[72ch]");
  });

  it("can opt out of the measure for surfaces that own their own width", () => {
    const { container } = render(<Page measure="full">x</Page>);
    expect(container.querySelector("main")!.className).toContain("max-w-none");
  });
});

describe("Section", () => {
  it("renders its heading at the level it was told, never one it guessed", () => {
    render(<Section title="Cast" level={3}>body</Section>);
    expect(screen.getByRole("heading", { level: 3, name: "Cast" })).toBeInTheDocument();
  });

  it("renders no heading chrome at all when given none", () => {
    const { container } = render(<Section>body</Section>);
    expect(container.querySelector("h2, h3, h4")).toBeNull();
  });
});

describe("Stack and Cluster", () => {
  it("apply a real gap class rather than an interpolated one", () => {
    // Tailwind scans source text, so `gap-${x}` compiles to nothing at all.
    const { container: a } = render(<Stack gap="xl">x</Stack>);
    expect(a.firstElementChild!.className).toContain("gap-xl");
    const { container: b } = render(<Cluster gap="2xs">x</Cluster>);
    expect(b.firstElementChild!.className).toContain("gap-2xs");
  });

  it("wraps by default — a non-wrapping control row is the 320px overflow", () => {
    const { container } = render(<Cluster>x</Cluster>);
    expect(container.firstElementChild!.className).toContain("flex-wrap");
  });

  it("can render as a list so grouped content keeps its semantics", () => {
    const { container } = render(<Stack as="ul">x</Stack>);
    expect(container.querySelector("ul")).not.toBeNull();
  });
});

describe("SkipLink", () => {
  it("is reachable by keyboard and points at the main landmark", async () => {
    const user = userEvent.setup();
    render(
      <>
        <SkipLink />
        <Page>content</Page>
      </>,
    );
    const link = screen.getByRole("link", { name: /skip to content/i });
    expect(link).toHaveAttribute("href", "#main");
    await user.tab();
    expect(link).toHaveFocus();
  });

  it("is visually hidden but NOT display:none — that would drop it from the tab order", () => {
    render(<SkipLink />);
    const link = screen.getByRole("link", { name: /skip to content/i });
    expect(link.className).toContain("sr-only");
    expect(link.className).not.toMatch(/\bhidden\b/);
    // It must have a focus-visible reveal, or it is permanently invisible.
    expect(link.className).toMatch(/focus-visible:/);
  });
});

describe("HeaderBar", () => {
  it("takes its height from --header-h rather than a per-bar pixel value", () => {
    const { container } = render(<HeaderBar>x</HeaderBar>);
    const header = container.querySelector("header")!;
    expect(header.className).toContain("h-header");
    expect(header.className).toContain("px-gutter");
    // The bar drifted 52px vs 50px and px-16/26 vs px-12/24 before this.
    expect(header.className).not.toMatch(/h-\[\d/);
    expect(header.className).not.toMatch(/px-\[\d/);
  });

  it("makes elevation a prop, not a copied box-shadow literal", () => {
    const { container: flat } = render(<HeaderBar>x</HeaderBar>);
    const { container: lifted } = render(<HeaderBar elevated>x</HeaderBar>);
    expect(flat.querySelector("header")!.className).not.toContain("shadow-md");
    expect(lifted.querySelector("header")!.className).toContain("shadow-md");
  });

  it("keeps the trailing control cluster from shrinking", () => {
    // A squeezed cluster pushes intrinsically-sized children 50-150px past the
    // edge; the fix for a crowded bar is collapsing controls, not shrinking.
    const { container } = render(<HeaderTrail>x</HeaderTrail>);
    expect(container.firstElementChild!.className).toContain("flex-none");
    const { container: lead } = render(<HeaderLead>x</HeaderLead>);
    expect(lead.firstElementChild!.className).toContain("min-w-0");
  });
});

describe("the frame is declared once, not per route", () => {
  it("declares the viewport, with zoom left alone", () => {
    const src = code("app/layout.tsx");
    expect(src).toMatch(/export const viewport: Viewport/);
    expect(src).toMatch(/width: "device-width"/);
    expect(src).toMatch(/initialScale: 1/);
    // Suppressing zoom is a WCAG 1.4.4 failure and is the wrong fix for the
    // iOS auto-zoom problem — that one is the >= 16px --fs-field floor.
    expect(src).not.toMatch(/userScalable/);
    expect(src).not.toMatch(/maximumScale/);
    // All-or-nothing with env(safe-area-inset-*); not adopted yet.
    expect(src).not.toMatch(/viewportFit:\s*"cover"/);
  });

  it("templates the brand suffix instead of every route retyping it", () => {
    const src = code("app/layout.tsx");
    expect(src).toMatch(/template: "%s · Mytheca"/);
  });

  it("ships route-level loading, error and not-found states", () => {
    for (const file of ["app/loading.tsx", "app/error.tsx", "app/not-found.tsx"]) {
      expect(readFileSync(file, "utf8").length).toBeGreaterThan(0);
    }
    // The error boundary is useless without a way back out of the error.
    expect(readFileSync("app/error.tsx", "utf8")).toContain("reset()");
  });

  it("has no bespoke header bar left outside the chassis", () => {
    for (const file of [
      "components/layout/AppHeader.tsx",
      "components/layout/SceneHeader.tsx",
      "features/options/OptionsView.tsx",
      "features/documents/DocumentsView.tsx",
    ]) {
      expect(code(file), file).not.toMatch(/<header className="mytheca-header/);
    }
  });
});

describe("theme-color", () => {
  it("mirrors every theme's --page-bg exactly", () => {
    // This is the one place a theme colour is duplicated outside the stylesheet,
    // because <meta name="theme-color"> cannot read a custom property.
    const css = readFileSync("styles/themes.css", "utf8");
    for (const key of THEME_KEYS) {
      const block = css.match(new RegExp(`\\.theme-${key}\\s*\\{([\\s\\S]*?)\\n\\}`))?.[1];
      expect(block, `theme-${key} block`).toBeTruthy();
      const pageBg = block!.match(/--page-bg:\s*(#[0-9a-fA-F]{6})/)?.[1];
      expect(pageBg?.toLowerCase()).toBe(THEME_PAGE_BG[key].toLowerCase());
    }
  });

  it("is retargeted whenever the theme class changes", () => {
    applyThemeClass("light");
    const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    expect(meta?.content).toBe(THEME_PAGE_BG.light);
    applyThemeClass("slate");
    expect(
      document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.content,
    ).toBe(THEME_PAGE_BG.slate);
  });
});
