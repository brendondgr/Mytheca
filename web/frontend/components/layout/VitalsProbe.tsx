"use client";

import { useEffect } from "react";

/**
 * Collects Core Web Vitals into `window.__mythecaVitals`, for
 * `utils/scripts/research/run_core_web_vitals.mjs` to read.
 *
 * **Flag-gated, and gated at the import too.** It renders nothing, subscribes to nothing,
 * and does not even load the `web-vitals` module unless `NEXT_PUBLIC_VITALS === "1"`. A
 * measurement probe that ships in a normal build is a probe that changes the thing it
 * measures — and `web-vitals` is a devDependency, so a production bundle must not reach for
 * it. `NEXT_PUBLIC_*` is inlined at build time, so the dynamic import below is statically
 * unreachable in a normal build and drops out entirely.
 */
export function VitalsProbe() {
  useEffect(() => {
    if (process.env.NEXT_PUBLIC_VITALS !== "1") return;
    let cancelled = false;

    void import("web-vitals").then(({ onCLS, onINP, onLCP }) => {
      if (cancelled) return;
      const store = ((window as unknown as { __mythecaVitals?: unknown[] }).__mythecaVitals ??= []);
      const push = (metric: { name: string; value: number; rating: string; id: string }) => {
        // The library can report the same metric more than once as it refines its answer
        // (LCP especially). Keep every entry and let the runner take the last per name —
        // discarding here would hide exactly the refinement that makes the value correct.
        store.push({ name: metric.name, value: metric.value, rating: metric.rating, id: metric.id });
      };
      onCLS(push);
      onINP(push);
      onLCP(push);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  return null;
}
