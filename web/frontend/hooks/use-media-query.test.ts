import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, afterEach } from "vitest";
import { useMediaQuery } from "./use-media-query";

const original = window.matchMedia;
afterEach(() => {
  window.matchMedia = original;
});

/** A controllable `matchMedia`, so a test can move the viewport. */
function stub(initial: number) {
  let width = initial;
  const listeners = new Set<() => void>();
  const seen: string[] = [];
  window.matchMedia = ((query: string) => {
    seen.push(query);
    return {
      get matches() {
        const min = Number(/min-width:\s*(\d+)px/.exec(query)?.[1] ?? NaN);
        return Number.isNaN(min) ? false : width >= min;
      },
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: (_: string, fn: () => void) => listeners.add(fn),
      removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
      dispatchEvent: () => false,
    } as unknown as MediaQueryList;
  }) as typeof window.matchMedia;
  return {
    seen,
    listeners,
    resize(next: number) {
      width = next;
      act(() => listeners.forEach((fn) => fn()));
    },
  };
}

describe("useMediaQuery", () => {
  it("answers for the current viewport", () => {
    stub(1024);
    const { result } = renderHook(() => useMediaQuery("(min-width: 640px)"));
    expect(result.current).toBe(true);
  });

  it("re-renders when the viewport crosses the query", () => {
    const mq = stub(320);
    const { result } = renderHook(() => useMediaQuery("(min-width: 640px)"));
    expect(result.current).toBe(false);

    mq.resize(1024);
    expect(result.current).toBe(true);

    mq.resize(500);
    expect(result.current).toBe(false);
  });

  it("returns false where matchMedia does not exist", () => {
    // jsdom does not implement it, and neither does the server. Anything gated on this must
    // be safe to be absent on the first paint — which is the correct posture for a
    // progressive enhancement, and why the header's SSR form is the narrow one.
    (window as { matchMedia?: unknown }).matchMedia = undefined;
    const { result } = renderHook(() => useMediaQuery("(min-width: 640px)"));
    expect(result.current).toBe(false);
  });

  it("unsubscribes on unmount", () => {
    const mq = stub(320);
    const { unmount } = renderHook(() => useMediaQuery("(min-width: 640px)"));
    expect(mq.listeners.size).toBeGreaterThan(0);
    unmount();
    expect(mq.listeners.size).toBe(0);
  });
});
