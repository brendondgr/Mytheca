import * as React from "react";
import { renderHook, render, screen, act } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { useExitTransition } from "./use-exit-transition";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useExitTransition", () => {
  it("mounts on the SAME render that opens, not on a later effect", () => {
    const { result, rerender } = renderHook(({ open }) => useExitTransition(open), {
      initialProps: { open: false },
    });
    expect(result.current.mounted).toBe(false);

    rerender({ open: true });
    // This is the load-bearing case: callers move focus into the element as
    // they open it (a menu focuses its first option). An effect-driven mount
    // would have them reaching into a node that does not exist yet.
    expect(result.current.mounted).toBe(true);
    expect(result.current.closing).toBe(false);
  });

  it("holds the element mounted and flagged while it animates out", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ open }) => useExitTransition(open, 140), {
      initialProps: { open: true },
    });

    rerender({ open: false });
    // Still on screen, and marked so CSS can transition it to the exit state.
    expect(result.current.mounted).toBe(true);
    expect(result.current.closing).toBe(true);

    act(() => void vi.advanceTimersByTime(139));
    expect(result.current.mounted).toBe(true);

    act(() => void vi.advanceTimersByTime(1));
    expect(result.current.mounted).toBe(false);
    expect(result.current.closing).toBe(false);
  });

  it("keeps the very same DOM node across the close, never remounting it", () => {
    vi.useFakeTimers();

    function Fixture({ open }: { open: boolean }) {
      const { mounted, closing } = useExitTransition(open, 140);
      return mounted
        ? React.createElement("div", {
            "data-testid": "panel",
            "data-closing": closing || undefined,
          })
        : null;
    }

    const { rerender } = render(React.createElement(Fixture, { open: true }));
    const beforeClose = screen.getByTestId("panel");

    rerender(React.createElement(Fixture, { open: false }));
    // Node *identity*, not just presence: if `closing` were deferred to an
    // effect the element would unmount and a different node would come back,
    // restarting the CSS transition from its entrance state and producing a
    // visible flicker instead of an exit.
    expect(screen.getByTestId("panel")).toBe(beforeClose);
    expect(beforeClose).toHaveAttribute("data-closing", "true");

    act(() => void vi.advanceTimersByTime(140));
    expect(screen.queryByTestId("panel")).toBeNull();
  });

  it("unmounts immediately under prefers-reduced-motion", () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("prefers-reduced-motion: reduce"),
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));

    const { result, rerender } = renderHook(({ open }) => useExitTransition(open), {
      initialProps: { open: true },
    });
    rerender({ open: false });

    // There is no exit to watch, so holding the node would only delay the
    // dismissal the user asked for.
    expect(result.current.mounted).toBe(false);
    expect(result.current.closing).toBe(false);
  });
});
