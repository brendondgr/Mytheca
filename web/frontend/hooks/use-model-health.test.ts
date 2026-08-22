import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useModelHealth, POLL_MS } from "./use-model-health";
import { getLlmHealth } from "@/lib/api";
import type { LlmHealth } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getLlmHealth: vi.fn(),
}));

const OK: LlmHealth = {
  state: "reachable",
  backend: "llamacpp",
  model: "test-model",
  checkedAt: "2026-08-22T00:00:00Z",
  detail: "test-model is served by this endpoint.",
};

function answers(value: LlmHealth) {
  vi.mocked(getLlmHealth).mockImplementation(() => Promise.resolve(value));
}

/**
 * Flush pending promises.
 *
 * `waitFor` cannot be used here: it polls on real timers, which `vi.useFakeTimers` has
 * replaced, so every assertion would hang until the test timeout. An `act` with an awaited
 * microtask is the equivalent that works under fake timers.
 */
async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

function setVisibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { value: state, configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("useModelHealth", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setVisibility("visible");
    answers(OK);
  });
  afterEach(() => vi.useRealTimers());

  it("checks once on mount", async () => {
    const { result } = renderHook(() => useModelHealth());
    await flush();
    expect(result.current.health).toEqual(OK);
  });

  it("re-checks on the poll interval", async () => {
    renderHook(() => useModelHealth());
    await flush();
    const first = vi.mocked(getLlmHealth).mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(POLL_MS);
    });
    expect(vi.mocked(getLlmHealth).mock.calls.length).toBeGreaterThan(first);
  });

  it("stops polling while the tab is hidden", async () => {
    renderHook(() => useModelHealth());
    await flush();

    act(() => setVisibility("hidden"));
    const atHide = vi.mocked(getLlmHealth).mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(POLL_MS * 3);
    });
    // A background tab polling forever is a request a minute for nothing, and the answer is
    // stale the instant the player returns anyway.
    expect(vi.mocked(getLlmHealth).mock.calls.length).toBe(atHide);
  });

  it("checks again the moment the tab comes back", async () => {
    renderHook(() => useModelHealth());
    await flush();
    act(() => setVisibility("hidden"));
    const atHide = vi.mocked(getLlmHealth).mock.calls.length;

    await act(async () => setVisibility("visible"));
    expect(vi.mocked(getLlmHealth).mock.calls.length).toBeGreaterThan(atHide);
  });

  it("re-checks on demand", async () => {
    const { result } = renderHook(() => useModelHealth());
    await flush();
    const before = vi.mocked(getLlmHealth).mock.calls.length;

    await act(async () => result.current.recheck());
    expect(vi.mocked(getLlmHealth).mock.calls.length).toBeGreaterThan(before);
  });

  it("keeps the last answer when the check itself fails", async () => {
    // The light must not cry wolf: this endpoint failing is not evidence about the model,
    // and a light that flashes red on an unrelated hiccup stops being read.
    const { result } = renderHook(() => useModelHealth());
    await flush();
    expect(result.current.health).toEqual(OK);

    vi.mocked(getLlmHealth).mockImplementation(() => Promise.reject(new Error("offline")));
    await act(async () => result.current.recheck());
    expect(result.current.health).toEqual(OK);
  });

  it("stops polling once unmounted", async () => {
    const { unmount } = renderHook(() => useModelHealth());
    await flush();
    unmount();
    const atUnmount = vi.mocked(getLlmHealth).mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(POLL_MS * 2);
    });
    expect(vi.mocked(getLlmHealth).mock.calls.length).toBe(atUnmount);
  });
});
