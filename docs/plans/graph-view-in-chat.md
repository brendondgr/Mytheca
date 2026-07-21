# Plan — In-Chat Story-Graph View (Chat ⇄ Graph switch)

## 1. Introduction

The story player currently reads only as a running transcript. This plan adds a
second **view mode** to that surface: a force-directed **Story-Graph** rendering
of the scenario's knowledge graph (characters, settings, and their relationships),
reachable via a **Chat ⇄ Graph switch** placed in the scene header immediately to
the **left of the Export button**. The graph is not fetched or its renderer loaded
until the user first switches to it.

The backend already exposes the data: `GET /api/scenarios/{id}/graph` →
`{ available, scenarioId, nodes[], edges[] }` (nodes `{ id, type, label, metadata }`,
edges `{ source, target, type, metadata }`), surfaced in the FE client as
`getScenarioGraph(scenarioId)` with matching `ScenarioGraph` types. No frontend
consumer exists yet — this UI is the first. The renderer is **`react-force-graph-2d`**
(canvas + d3-force under the hood — the approach in the reference), chosen because
the graph is meant to **grow and interconnect many more entity types over time** and
the canvas engine scales to large graphs. It declares `peerDependencies: { react: '*' }`,
so it is compatible with the repo's React 19 / Next 16 with no overrides. It reads
`window` at import, so it is loaded through `next/dynamic({ ssr: false })` — which
also gives the "not loaded until switched to" behavior (a separate lazy chunk).

Scope is **frontend-only** — no backend or contract change. Chrome (panel background,
header switch) uses the theme tokens; **nodes/edges are uniquely colored by type**
via a dedicated palette with a deterministic fallback so brand-new types added later
automatically get a stable, distinct color (the "expandable" requirement).

## 2. Gaps & Unanswered Questions

- **Composer in graph mode** *(assumption)*: the switch swaps the whole center column
  (transcript scroll + composer) for the graph view; the composer is hidden while
  viewing the graph (you are inspecting, not speaking). The left Cast rail and right
  Director rail stay for continuity.
- **Node interaction** *(assumption)*: clicking a `Character` node opens the existing
  right-rail `CharacterDossier` via the story player's `openProfile` (reuse, no new
  UI). Other node types are non-interactive beyond the hover tooltip in v1.
- **`available: false`** (Neo4j off/unreachable) → a friendly, themed empty/unavailable
  state, not an error. Empty graph (available but 0 nodes) → its own empty state.
- **Accessibility** *(decided, per `ui/data-viz.md`)*: canvas has no focusable DOM
  nodes, so the graph view always renders a visually-hidden description + an
  accessible `<table>` of nodes and edges as the screen-reader/keyboard alternative,
  plus a visible legend labeling each type→color (never color alone).

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Dependency + color/data helpers

- **Locations:** `web/frontend/package.json` (+ lockfile) via `npm install react-force-graph-2d`;
  new `web/frontend/lib/graphColors.ts`; new test `web/frontend/lib/graphColors.test.ts`;
  docs `docs/workflow.md` (new dependency + note), `docs/architecture.md` (dependency
  purpose), `docs/design-system.md` (graph node/edge palette + legend rule).
- **What:** `graphColors.ts` exports `nodeColor(type)` / `edgeColor(type)` mapping the
  known Story-Graph types (`Character`, `Setting`, `Event`, `Secret`, `Faction`,
  `Consequence`, relationship edge types like `present_at`, `loves`) to distinct hexes
  drawn from `PALETTE` (`lib/seed-data.ts`) + the semantic colors, with a **deterministic
  string-hash fallback** into a fixed hue wheel so any future/unknown type gets a stable
  distinct color. Also `graphLegend(nodes, edges)` → the de-duplicated `{ type, color, kind }`
  list the legend and swatches render from.
- **Rationale:** Pure, dependency-light helpers land first with their own fast unit test;
  they encode the "expandable to many more types" requirement independently of any React.
- **Action:** `npm test -- graphColors` + `npm run typecheck`. Commit:
  `Story-Graph View (1/4) Complete: add react-force-graph-2d dep + deterministic type→color helpers.`

### Phase 2 — GraphCanvas (isolated renderer) + GraphView (states, a11y, legend)

- **Locations:** new `web/frontend/components/feature/GraphCanvas.tsx`,
  `web/frontend/components/feature/GraphView.tsx`,
  `web/frontend/components/feature/GraphView.test.tsx`.
- **What:**
  - `GraphCanvas.tsx` — `"use client"`; `next/dynamic(() => import("react-force-graph-2d"), { ssr:false })`;
    a wrapper `<div>` measured by `ResizeObserver` (canvas needs explicit px w/h);
    `nodeCanvasObject` hand-draws each node (filled `arc` in `nodeColor(type)` + a name
    label in the live themed ink color) with selection/hover ring scaled by `globalScale`;
    links use `linkColor` from `edgeColor(type)`; `backgroundColor` transparent so the
    themed wrapper shows through; `warmupTicks`/`cooldownTicks`/`cooldownTime` tuned to
    settle-then-freeze; `nodeLabel` tooltip (`name — type`); optional `onNodeClick`
    (Character → `onNodeSelect(id)`). Live theme text/hairline colors read via
    `getComputedStyle(document.documentElement)` on `--ink`/`--hair`, refreshed on
    `useTheme()` change. This file is the sole importer of the library.
  - `GraphView.tsx` — `"use client"`; on mount calls `getScenarioGraph(scenarioId)`
    (so nothing fetches until this component is rendered, i.e. graph mode is on);
    renders **loading**, **unavailable** (`available:false`), **empty** (0 nodes),
    **error**, and **populated** states; a **visible legend** (type label + color swatch);
    an always-present **sr-only description + `<table>`** of nodes and edges; and the
    themed panel wrapping `<GraphCanvas>`.
- **Rationale:** Isolating the canvas library in `GraphCanvas` keeps `GraphView` (and its
  tests) renderable in jsdom — tests mock `@/components/feature/GraphCanvas` and
  `getScenarioGraph` and assert the state machine + the accessible table, never touching
  canvas.
- **Action:** `npm test -- GraphView` + `npm run typecheck`; a11y pass (keyboard-reachable
  table, focus-visible on the figure, legend labels not color-alone). Commit:
  `Story-Graph View (2/4) Complete: GraphCanvas force renderer + accessible GraphView with all states + legend.`

### Phase 3 — Chat ⇄ Graph switch in the header + wire into the story player

- **Locations:** `web/frontend/components/layout/SceneHeader.tsx` (+ `SceneHeader.test.tsx`
  if present, else assert via the view test), `web/frontend/features/story-player/StoryPlayerView.tsx`
  (+ `StoryPlayerView.test.tsx`).
- **What:** add a segmented **Chat | Graph** control (`role="group"`, two `aria-pressed`
  buttons, mirroring `ThemeSwitcher`/the Inspector pill idiom, `bg-field`/`border-field-bd`,
  active = accent) rendered **left of `<ExportMenu>`** in the header's right cluster; new
  `viewMode` / `onViewModeChange` props on `SceneHeader`. In `StoryPlayerView`, add
  `viewMode` state (`'chat' | 'graph'`, default `'chat'`), pass it to the header, and
  conditionally render the center column: **chat** (existing transcript + `Composer`) or
  `<GraphView scenarioId={scenario.id} onNodeSelect={scene.openProfile} />`. Rails and
  header stay mounted across the switch.
- **Rationale:** The switch is the user's requested entry point; `GraphView` mounting only
  in graph mode is what defers the fetch + the dynamic-import chunk.
- **Action:** `npm test -- SceneHeader StoryPlayerView` + `npm run typecheck` + `npm run lint`;
  responsive pass at 320/375/768/1024 (switch fits the 50px header without overflow; graph
  fills the center column) across all three themes. Commit:
  `Story-Graph View (3/4) Complete: header Chat/Graph switch wired to swap transcript for the graph.`

### Phase 4 — Full validation gate + docs + merge

- **Locations:** `docs/component-map.md` (GraphView/GraphCanvas), `docs/design-system.md`
  (story-player graph mode + legend), `docs/story-graph-neo4j.md` ("Graph visualization UI"
  seam → implemented), `docs/checklist.md` (new entry), this plan.
- **What:** run the whole gate — `npm test` (full vitest), `npm run typecheck`, `npm run lint`,
  `npm run build`, and `uv run pytest` (confirm the 784 backend tests still green — no backend
  change). Final a11y + responsive + three-theme pass. Update docs; add checklist entry.
  Merge `graph-view-in-chat` → `main`.
- **Action:** After the gate is green and docs updated, commit:
  `Story-Graph View (4/4) Complete: full validation gate green + docs + merge to main.`

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Graph dependency | `react-force-graph-2d` (canvas + d3-force engine), lazy-loaded | `web/frontend/package.json` |
| Color/data helpers | `nodeColor`/`edgeColor`/`graphLegend` with deterministic type→color fallback | `web/frontend/lib/graphColors.ts` |
| Graph renderer | Isolated `next/dynamic(ssr:false)` force-graph canvas wrapper, themed text, pan/zoom, node click | `web/frontend/components/feature/GraphCanvas.tsx` |
| Graph view | Fetch + state machine (loading/unavailable/empty/error/populated) + legend + sr-only table | `web/frontend/components/feature/GraphView.tsx` |
| View switch | Chat ⇄ Graph segmented control left of Export | `web/frontend/components/layout/SceneHeader.tsx` |
| Story-player wiring | `viewMode` state swapping transcript↔graph | `web/frontend/features/story-player/StoryPlayerView.tsx` |
| Helper tests | Deterministic color mapping | `web/frontend/lib/graphColors.test.ts` |
| View tests | State machine + accessible table + legend (GraphCanvas mocked) | `web/frontend/components/feature/GraphView.test.tsx` |
| Switch/wiring tests | Switch aria-pressed + transcript↔graph swap | `web/frontend/components/layout/SceneHeader.test.tsx`, `web/frontend/features/story-player/StoryPlayerView.test.tsx` |
