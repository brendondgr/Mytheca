import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, act, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { useReveal } from "@/hooks/use-reveal";

/**
 * The reveal system's contract is not "does it animate" — jsdom cannot answer
 * that. It is "can it ever leave content hidden", and the answer must be no
 * down every path.
 */

type Observed = { target: Element };

class MockIO {
  static instances: MockIO[] = [];
  observed = new Set<Element>();
  unobserved: Element[] = [];
  disconnected = false;
  constructor(
    public cb: (entries: { target: Element; isIntersecting: boolean }[]) => void,
    public options: IntersectionObserverInit,
  ) {
    MockIO.instances.push(this);
  }
  observe(el: Element) { this.observed.add(el); }
  unobserve(el: Element) { this.observed.delete(el); this.unobserved.push(el); }
  disconnect() { this.disconnected = true; }
  fire(els: Element[]) {
    this.cb(els.map((target) => ({ target, isIntersecting: true })));
  }
}

function Harness({ enabled = true }: { enabled?: boolean }) {
  useReveal(enabled);
  return null;
}

/** Place an element below the fold, or on screen, by faking its box. */
function placeElement(el: HTMLElement, top: number, height = 100) {
  el.getBoundingClientRect = () =>
    ({ top, bottom: top + height, height, left: 0, right: 0, width: 100, x: 0, y: top, toJSON() {} }) as DOMRect;
}

const originalIO = globalThis.IntersectionObserver;
const originalMutation = globalThis.MutationObserver;

beforeEach(() => {
  MockIO.instances = [];
  document.documentElement.className = "";
  document.body.innerHTML = "";
  // Default: an engine WITHOUT view(), which is the only case the hook acts on.
  vi.stubGlobal("CSS", { supports: () => false });
  vi.stubGlobal("IntersectionObserver", MockIO as unknown as typeof IntersectionObserver);
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener() {}, removeEventListener() {} }) as never;
});

afterEach(() => {
  vi.unstubAllGlobals();
  globalThis.IntersectionObserver = originalIO;
  globalThis.MutationObserver = originalMutation;
});

describe("useReveal — fail-open", () => {
  it("does nothing at all where CSS already drives reveals", () => {
    // Chromium: `animation-timeline: view()` runs the pure-CSS path. Adding the
    // class here would run two entrances on one element.
    vi.stubGlobal("CSS", { supports: () => true });
    render(<Harness />);
    expect(document.documentElement.classList.contains("js-reveal")).toBe(false);
    expect(MockIO.instances).toHaveLength(0);
  });

  it("does nothing where IntersectionObserver is unavailable", () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    render(<Harness />);
    // No observer means nothing would ever un-hide, so nothing may be hidden.
    expect(document.documentElement.classList.contains("js-reveal")).toBe(false);
  });

  it("does nothing when the user asked for reduced motion", () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener() {}, removeEventListener() {} }) as never;
    render(<Harness />);
    expect(document.documentElement.classList.contains("js-reveal")).toBe(false);
  });

  it("adds the root class only after the observer exists", () => {
    render(<Harness />);
    expect(MockIO.instances).toHaveLength(1);
    expect(document.documentElement.classList.contains("js-reveal")).toBe(true);
  });
});

describe("useReveal — what gets hidden", () => {
  it("never hides an element already on screen", () => {
    const el = document.createElement("div");
    el.className = "reveal";
    document.body.appendChild(el);
    placeElement(el, 100); // within innerHeight
    render(<Harness />);
    // Straight to shown: no pending, so no flash, and no dependence on the
    // observer firing for content the user is already looking at.
    expect(el.dataset.reveal).toBe("shown");
    expect(MockIO.instances[0].observed.has(el)).toBe(false);
  });

  it("hides only what is below the fold, and reveals it on intersection", () => {
    const el = document.createElement("div");
    el.className = "reveal";
    document.body.appendChild(el);
    placeElement(el, window.innerHeight + 500);
    render(<Harness />);
    expect(el.dataset.reveal).toBe("pending");

    act(() => MockIO.instances[0].fire([el]));
    expect(el.dataset.reveal).toBe("shown");
  });

  it("unobserves in the callback — a long list must not pay geometry forever", () => {
    const el = document.createElement("div");
    el.className = "reveal";
    document.body.appendChild(el);
    placeElement(el, window.innerHeight + 500);
    render(<Harness />);
    act(() => MockIO.instances[0].fire([el]));
    expect(MockIO.instances[0].unobserved).toContain(el);
  });

  it("uses threshold 0 and a px rootMargin", () => {
    render(<Harness />);
    const { options } = MockIO.instances[0];
    // A section taller than the viewport can never reach ratio 0.5, and
    // rootMargin throws SyntaxError on em/rem/vh.
    expect(options.threshold).toBe(0);
    expect(options.rootMargin).toMatch(/px|%/);
    expect(options.rootMargin).not.toMatch(/r?em|vh|vw/);
  });

  it("reveals everything still pending after a bfcache restore", () => {
    const el = document.createElement("div");
    el.className = "reveal";
    document.body.appendChild(el);
    placeElement(el, window.innerHeight + 500);
    render(<Harness />);
    expect(el.dataset.reveal).toBe("pending");

    // Registrations survive a back navigation but produce no new entries.
    act(() => {
      const event = new Event("pageshow") as PageTransitionEvent;
      Object.defineProperty(event, "persisted", { value: true });
      window.dispatchEvent(event);
    });
    expect(el.dataset.reveal).toBe("shown");
  });

  it("picks up elements appended after mount", async () => {
    render(<Harness />);
    const el = document.createElement("div");
    el.className = "reveal";
    placeElement(el, window.innerHeight + 500);
    document.body.appendChild(el);
    // The MutationObserver is async by spec.
    await waitFor(() => expect(el.dataset.reveal).toBe("pending"));
  });

  it("leaves nothing hidden on unmount", () => {
    const el = document.createElement("div");
    el.className = "reveal";
    document.body.appendChild(el);
    placeElement(el, window.innerHeight + 500);
    const { unmount } = render(<Harness />);
    expect(el.dataset.reveal).toBe("pending");
    unmount();
    expect(document.documentElement.classList.contains("js-reveal")).toBe(false);
    expect(el.hasAttribute("data-reveal")).toBe(false);
  });
});

describe("the reveal stylesheet", () => {
  const css = readFileSync("styles/motion.css", "utf8");

  it("gives .reveal no base hidden state", () => {
    // A static `opacity: 0` on reveal content is the permanent-blank-page
    // hazard the whole design exists to avoid.
    const base = css.match(/\n\.reveal \{([\s\S]*?)\n\}/)?.[1] ?? "";
    expect(base).not.toMatch(/opacity\s*:\s*0/);
    expect(base).not.toMatch(/visibility\s*:\s*hidden/);
    expect(base).not.toMatch(/transform\s*:/);
  });

  it("gates the CSS path on both support and reduced-motion", () => {
    expect(css).toMatch(
      /@supports \(animation-timeline: view\(\)\) \{\s*@media \(prefers-reduced-motion: no-preference\)/,
    );
  });

  it("declares animation-timeline AFTER the shorthand, which resets it", () => {
    const block = css.match(/\.reveal \{\s*animation:[\s\S]*?\n {4}\}/)?.[0] ?? "";
    expect(block).toBeTruthy();
    expect(block.indexOf("animation:")).toBeLessThan(block.indexOf("animation-timeline:"));
  });

  it("scopes the JS path under all four gates", () => {
    const fallback = css.match(
      /@supports not \(animation-timeline: view\(\)\) \{[\s\S]*?\n\}/,
    )?.[0];
    expect(fallback).toBeTruthy();
    expect(fallback).toContain("prefers-reduced-motion: no-preference");
    expect(fallback).toContain(".js-reveal");
    expect(fallback).toContain('[data-reveal="pending"]');
  });

  it("animates only compositable properties", () => {
    const frames = css.match(/@keyframes mythecaRevealIn \{[\s\S]*?\n\}/)?.[0] ?? "";
    expect(frames).toMatch(/opacity/);
    expect(frames).toMatch(/transform/);
    expect(frames).not.toMatch(/\b(width|height|top|left|margin)\s*:/);
  });
});
