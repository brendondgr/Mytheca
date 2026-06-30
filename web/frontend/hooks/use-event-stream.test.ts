import { describe, it, expect } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useEventStream } from "./use-event-stream";

async function* fromList<T>(items: T[]): AsyncGenerator<T> {
  for (const item of items) yield item;
}

describe("useEventStream", () => {
  it("forwards each frame in order and ends in 'done'", async () => {
    const seen: number[] = [];
    const { result } = renderHook(() => useEventStream<number>((n) => seen.push(n)));
    await act(async () => {
      await result.current.run(() => fromList([1, 2, 3]));
    });
    expect(seen).toEqual([1, 2, 3]);
    expect(result.current.status).toBe("done");
  });

  it("sets 'error' status and rethrows on a stream failure", async () => {
    async function* boom(): AsyncGenerator<number> {
      yield 1;
      throw new Error("upstream");
    }
    const { result } = renderHook(() => useEventStream<number>(() => {}));
    await act(async () => {
      await expect(result.current.run(() => boom())).rejects.toThrow("upstream");
    });
    await waitFor(() => expect(result.current.status).toBe("error"));
  });

  it("abort() is safe to call when idle", () => {
    const { result } = renderHook(() => useEventStream<number>(() => {}));
    act(() => result.current.abort());
    expect(result.current.status).toBe("idle");
  });
});
