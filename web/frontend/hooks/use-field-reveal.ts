"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** One field to reveal, in the order the agent "writes" it. */
export interface RevealField<K extends string = string> {
  key: K;
  value: unknown;
}

export interface FieldRevealState<K extends string = string> {
  /** Values revealed so far, keyed by field key. */
  values: Partial<Record<K, unknown>>;
  /** The field being written *right now* (null before start / after done). */
  activeKey: K | null;
  /** True once every field has been revealed. */
  done: boolean;
}

/** Default cadence — fast enough to feel like live typing, slow enough to read. */
export const REVEAL_INTERVAL_MS = 150;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Choreographs a field-by-field reveal of an already-final result (the "filling
 * in this field, then that field" animation). `start(fields)` walks the ordered
 * list one tick at a time, exposing `values` (populated so far), `activeKey`
 * (the field being written now, for a `.velora-field-active` highlight), and
 * `done`. Under `prefers-reduced-motion` — or an empty list — everything is
 * revealed at once. A new `start` or unmount cancels any in-flight reveal.
 *
 * Purely presentational: the values are already final, so the reveal never gates
 * saving and callers may override any field at any time.
 */
export function useFieldReveal<K extends string = string>(
  intervalMs: number = REVEAL_INTERVAL_MS,
) {
  const [state, setState] = useState<FieldRevealState<K>>({
    values: {},
    activeKey: null,
    done: false,
  });
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clear = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    clear();
    setState({ values: {}, activeKey: null, done: false });
  }, [clear]);

  const start = useCallback(
    (fields: RevealField<K>[]) => {
      clear();

      if (fields.length === 0) {
        setState({ values: {}, activeKey: null, done: true });
        return;
      }

      if (prefersReducedMotion()) {
        const values = Object.fromEntries(
          fields.map((f) => [f.key, f.value]),
        ) as Partial<Record<K, unknown>>;
        setState({ values, activeKey: null, done: true });
        return;
      }

      // Pre-highlight the first field, then reveal one per tick.
      setState({ values: {}, activeKey: fields[0].key, done: false });
      let i = 0;
      const step = () => {
        const field = fields[i];
        setState((prev) => ({
          values: { ...prev.values, [field.key]: field.value },
          activeKey: field.key,
          done: false,
        }));
        i += 1;
        if (i < fields.length) {
          timerRef.current = setTimeout(step, intervalMs);
        } else {
          timerRef.current = setTimeout(() => {
            setState((prev) => ({ ...prev, activeKey: null, done: true }));
          }, intervalMs);
        }
      };
      timerRef.current = setTimeout(step, intervalMs);
    },
    [clear, intervalMs],
  );

  useEffect(() => clear, [clear]);

  return { ...state, start, reset };
}
