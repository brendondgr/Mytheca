"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Lifecycle of a turn stream. */
export type StreamStatus = "idle" | "streaming" | "done" | "error";

/**
 * Consume an NDJSON event stream, forwarding each parsed frame to `onEvent` and
 * tracking lifecycle. Decoupled from any endpoint: `run` takes a factory that, given
 * an `AbortSignal`, returns the async generator (e.g. `api.postTurn`). A new `run`
 * aborts the previous stream; the stream is aborted on unmount. Aborts are silent
 * (not surfaced as errors).
 */
export function useEventStream<T>(onEvent: (frame: T) => void) {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const onEventRef = useRef(onEvent);
  const abortRef = useRef<AbortController | null>(null);

  // Keep the latest callback without re-creating `run` (handlers fire post-render).
  useEffect(() => {
    onEventRef.current = onEvent;
  });

  useEffect(() => () => abortRef.current?.abort(), []);

  const abort = useCallback(() => abortRef.current?.abort(), []);

  const run = useCallback(
    async (factory: (signal: AbortSignal) => AsyncGenerator<T>): Promise<void> => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setStatus("streaming");
      try {
        for await (const frame of factory(controller.signal)) {
          if (controller.signal.aborted) return;
          onEventRef.current(frame);
        }
        if (!controller.signal.aborted) setStatus("done");
      } catch (err) {
        if (controller.signal.aborted || (err as DOMException)?.name === "AbortError") return;
        setStatus("error");
        throw err;
      }
    },
    [],
  );

  return { status, run, abort };
}
