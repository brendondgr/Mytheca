import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useFieldReveal, REVEAL_INTERVAL_MS } from "./use-field-reveal";

const FIELDS = [
  { key: "a", value: "A" },
  { key: "b", value: "B" },
  { key: "c", value: "C" },
];

describe("useFieldReveal", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("reveals fields one at a time, in order, then finishes", () => {
    const { result } = renderHook(() => useFieldReveal());

    act(() => result.current.start(FIELDS));
    // Pre-highlights the first field before any value lands.
    expect(result.current.activeKey).toBe("a");
    expect(result.current.values).toEqual({});
    expect(result.current.done).toBe(false);

    act(() => void vi.advanceTimersByTime(REVEAL_INTERVAL_MS));
    expect(result.current.values).toEqual({ a: "A" });
    expect(result.current.activeKey).toBe("a");

    act(() => void vi.advanceTimersByTime(REVEAL_INTERVAL_MS));
    expect(result.current.values).toEqual({ a: "A", b: "B" });
    expect(result.current.activeKey).toBe("b");

    act(() => void vi.advanceTimersByTime(REVEAL_INTERVAL_MS));
    expect(result.current.values).toEqual({ a: "A", b: "B", c: "C" });
    expect(result.current.activeKey).toBe("c");

    // One more tick clears the active field and marks done.
    act(() => void vi.advanceTimersByTime(REVEAL_INTERVAL_MS));
    expect(result.current.activeKey).toBeNull();
    expect(result.current.done).toBe(true);
  });

  it("reveals everything at once under reduced motion", () => {
    const spy = vi
      .spyOn(window, "matchMedia")
      .mockReturnValue({ matches: true } as MediaQueryList);

    const { result } = renderHook(() => useFieldReveal());
    act(() => result.current.start(FIELDS));

    expect(result.current.values).toEqual({ a: "A", b: "B", c: "C" });
    expect(result.current.activeKey).toBeNull();
    expect(result.current.done).toBe(true);
    spy.mockRestore();
  });

  it("finishes immediately for an empty field list", () => {
    const { result } = renderHook(() => useFieldReveal());
    act(() => result.current.start([]));
    expect(result.current.done).toBe(true);
    expect(result.current.activeKey).toBeNull();
  });

  it("reset() clears revealed state and cancels an in-flight reveal", () => {
    const { result } = renderHook(() => useFieldReveal());
    act(() => result.current.start(FIELDS));
    act(() => void vi.advanceTimersByTime(REVEAL_INTERVAL_MS));
    expect(result.current.values).toEqual({ a: "A" });

    act(() => result.current.reset());
    expect(result.current.values).toEqual({});
    expect(result.current.activeKey).toBeNull();
    expect(result.current.done).toBe(false);

    // No pending timer resurrects the reveal.
    act(() => void vi.advanceTimersByTime(REVEAL_INTERVAL_MS * 5));
    expect(result.current.values).toEqual({});
  });

  it("a new start() cancels the previous reveal", () => {
    const { result } = renderHook(() => useFieldReveal());
    act(() => result.current.start(FIELDS));
    act(() => void vi.advanceTimersByTime(REVEAL_INTERVAL_MS));

    act(() => result.current.start([{ key: "x", value: "X" }]));
    expect(result.current.values).toEqual({});
    expect(result.current.activeKey).toBe("x");

    act(() => void vi.advanceTimersByTime(REVEAL_INTERVAL_MS));
    expect(result.current.values).toEqual({ x: "X" });
  });
});
