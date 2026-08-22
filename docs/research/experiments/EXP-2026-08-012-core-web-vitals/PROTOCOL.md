# PROTOCOL — EXP-2026-08-012 Core web vitals

> Written before the run. No measurement had been taken when this file was committed;
> the first numbers were produced by the entrypoint below.

## Question

What are Mytheca's Core Web Vitals — CLS, INP and LCP — on a real production bundle,
under the 4× CPU throttling `docs/frontend-polish-spec.md` §14 specifies?

This has never been measurable. `next/font/google` fetched at build time, so `next build`
hard-failed with no network and the repository had no production bundle to profile.
`docs/plans/reach.md` Phase 9 removed that blocker; this is the first measurement.

## Hypothesis

Stated ahead of the run, from the structural work already done (space-reserved images via
`SmartImage`, a reserved error line in `FieldError`, a min-height on the streaming beat,
skeletons matching real card geometry, and metric-compatible font fallbacks):

**H1 — CLS passes.** Both routes score CLS < 0.1. The causes of shift were addressed
structurally on 2026-08-12 and the font swap now has a metric-compatible fallback.

**H2 — LCP passes on the Library.** `/` renders from a static prerender with no
third-party font connection on the critical path, so LCP < 2.5s at 4× throttle.

**H3 — INP is the weakest of the three.** The story player is the interaction surface and
it streams; if anything misses its threshold it is INP on `/{storylineId}/{scenarioId}`.

## Setup

- Bundle: `npm run build` output served by `npm run start` on port 3346 (production mode,
  not the dev server — dev-mode numbers would be meaningless).
- Probe: `web/frontend/components/layout/VitalsProbe.tsx`, mounted from `app/layout.tsx`
  **only** when `NEXT_PUBLIC_VITALS === "1"`. It subscribes to the `web-vitals` package's
  `onCLS`/`onINP`/`onLCP` and pushes entries onto `window.__mythecaVitals`. With the flag
  unset it renders nothing and subscribes to nothing, so a normal build is unaffected.
- Driver: `utils/scripts/research/run_core_web_vitals.mjs`, `puppeteer-core` against the
  system Chromium, with `Emulation.setCPUThrottlingRate: 4`.
- Backend: the FastAPI dev server on 3345, so the routes load real data.

## Data

Two routes, both served from the repository's own seeded content — which makes these
numbers specific to this world's size and not a general claim:

| Route | Why |
| --- | --- |
| `/` | The Library. The LCP surface: the app's landing page and its largest paint. |
| `/{storylineId}/{scenarioId}` | The story player. The INP surface, because it streams. |

The storyline/scenario ids are read from the running backend at run time and recorded in
`data/metrics.json`, so the exact target is reproducible.

## Metrics

| Metric | Definition | Direction |
| --- | --- | --- |
| `CLS` | Cumulative Layout Shift as reported by `web-vitals` `onCLS`, the largest burst of unexpected shift over the page's lifetime, unitless. Reported at page dismissal via the library's final-value callback. | lower is better |
| `INP` | Interaction to Next Paint in ms, as reported by `onINP` after a scripted interaction sequence. The worst interaction latency observed, not the mean. | lower is better |
| `LCP` | Largest Contentful Paint in ms from navigation start, as reported by `onLCP`. | lower is better |

Each is collected on `n = 5` cold loads per route (fresh browser context, no cache), and
reported as mean ± std over those loads.

## Baselines

None. There is no prior measurement to compare against — that is the point of the
experiment. The comparison is against the **pre-registered thresholds** below, which come
from `docs/frontend-polish-spec.md` §14 and Google's "good" bands:

- CLS < 0.1
- INP < 200 ms
- LCP < 2.5 s

## Procedure

```bash
# 1. Build the production bundle (needs no network since the fonts were self-hosted).
cd web/frontend && npm run build

# 2. Backend up, for real data on both routes.
uv run python app.py backend

# 3. Measure. Serves the bundle, drives Chromium at 4x CPU throttle, writes
#    data/metrics.json and data/raw.json.
node utils/scripts/research/run_core_web_vitals.mjs
```

Seeds: none — there is no sampling to seed. Run-to-run variance is machine noise and is
reported as the std over the 5 loads.

## What would falsify this

- **H1 is wrong** if either route reports mean CLS ≥ 0.1.
- **H2 is wrong** if `/` reports mean LCP ≥ 2500 ms.
- **H3 is wrong** if a metric other than INP is the one that misses its threshold, or if
  INP passes while something else fails.

If a route fails to load or the probe returns no entries, that route is recorded as failed
in `ISSUES.md` and **no aggregate is reported across the surviving route** — survivors are
not a random subsample (`EXP-2026-08-001` is this repository's worked example of getting
that wrong).
