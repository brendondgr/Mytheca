import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { useDelayedFlag, INDICATOR_DELAY_MS } from "./use-delayed-flag";

afterEach(() => vi.useRealTimers());

describe("useDelayedFlag", () => {
  it("shows nothing for a wait shorter than the gate", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ active }) => useDelayedFlag(active), {
      initialProps: { active: true },
    });

    // A 150ms request: the indicator must never have appeared. A spinner that
    // flashes and vanishes reads as slower than no spinner at all.
    act(() => void vi.advanceTimersByTime(150));
    expect(result.current).toBe(false);

    rerender({ active: false });
    act(() => void vi.advanceTimersByTime(1000));
    expect(result.current).toBe(false);
  });

  it("shows the indicator once the wait becomes perceptible", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useDelayedFlag(true));

    act(() => void vi.advanceTimersByTime(INDICATOR_DELAY_MS - 1));
    expect(result.current).toBe(false);

    act(() => void vi.advanceTimersByTime(1));
    expect(result.current).toBe(true);
  });

  it("clears the moment the wait ends", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ active }) => useDelayedFlag(active), {
      initialProps: { active: true },
    });
    act(() => void vi.advanceTimersByTime(INDICATOR_DELAY_MS));
    expect(result.current).toBe(true);

    rerender({ active: false });
    expect(result.current).toBe(false);
  });

  it("restarts the gate for a second wait", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ active }) => useDelayedFlag(active), {
      initialProps: { active: true },
    });
    act(() => void vi.advanceTimersByTime(INDICATOR_DELAY_MS));
    rerender({ active: false });

    // The next request gets its own full grace period rather than inheriting
    // the previous one's expired timer.
    rerender({ active: true });
    expect(result.current).toBe(false);
    act(() => void vi.advanceTimersByTime(INDICATOR_DELAY_MS));
    expect(result.current).toBe(true);
  });
});
