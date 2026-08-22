"use client";

import { useCallback, useEffect, useState } from "react";
import { getLlmHealth } from "@/lib/api";
import type { LlmHealth } from "@/lib/types";

/** How often to re-check while the tab is visible. */
export const POLL_MS = 60_000;

/**
 * Whether the configured model endpoint is actually usable.
 *
 * A player on a local model otherwise learns their endpoint died by sending a turn and
 * waiting out `LLM_GEN_TIMEOUT_SECONDS` — five minutes to be told nothing.
 *
 * Three deliberate behaviours:
 *
 * - **Paused while the tab is hidden.** A background tab polling a health endpoint forever is
 *   a request a minute for nothing, and the answer is stale the instant the player returns
 *   anyway — so it re-checks on becoming visible instead.
 * - **Re-checked on demand** (`recheck`), which the scene calls after a stream error. That is
 *   the moment the player most needs to know whether the failure was their endpoint.
 * - **A failed check is not a state.** If the health request itself fails we keep the last
 *   known answer rather than flashing "unreachable" at a player whose model is fine and whose
 *   own backend hiccuped — the light must not cry wolf, or it stops being read.
 */
export function useModelHealth(): { health: LlmHealth | null; recheck: () => void } {
  const [health, setHealth] = useState<LlmHealth | null>(null);

  const check = useCallback(async () => {
    try {
      setHealth(await getLlmHealth());
    } catch {
      // Keep the previous answer. See the docstring: this endpoint failing is not evidence
      // about the model.
    }
  }, []);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (timer !== null) return;
      void check();
      timer = setInterval(() => void check(), POLL_MS);
    };
    const stop = () => {
      if (timer === null) return;
      clearInterval(timer);
      timer = null;
    };
    const onVisibility = () => (document.visibilityState === "hidden" ? stop() : start());

    onVisibility();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [check]);

  return { health, recheck: () => void check() };
}
