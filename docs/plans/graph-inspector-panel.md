# Plan — Graph-mode Inspector Panel (type breakdown + node/edge properties)

## 1. Introduction

Extends the story player's **Graph view**. When in Graph mode, the right rail
becomes a **Graph Inspector**: an **overview** listing the node-type and
edge-type breakdown (type · color · count), and — on selecting a node or edge in
the canvas — a **detail** view of that element's properties (its `metadata` bag
plus identity). The scenario graph endpoint already returns rich `metadata` on
every node (appearance, traits, goal, personality, secret, …) and edge
(visibility, weight, status), so this is a frontend-only change.

The graph fetch + selection state live in `GraphView` (which mounts only in Graph
mode). `GraphView` renders the canvas **and** the inspector rail as siblings (a
fragment), so both share the same data/selection without lifting into
`StoryPlayerView`. Clicking a node/edge selects it (canvas highlights it, rail
shows its properties); clicking the background clears back to the overview. This
**replaces** the previous "Character node click → dossier" behavior. In Graph
mode the chat's Director rail and Turn Inspector are not shown.

## 2. Gaps & Unanswered Questions

- **Right-rail visibility** *(assumption)*: mirror `DirectorRail`'s `hidden … lg:block`
  so the inspector shows on desktop; on `< lg` the rails already collapse — a
  mobile drawer for the inspector is a documented follow-up.
- **`secret` in node metadata** *(assumption)*: the inspector is an author-facing
  diagnostic (like the Turn Inspector), so it shows **all** metadata the endpoint
  returns, including `secret`. (The read-only in-play dossier still hides it.)
- **Legend** *(decided)*: the old bottom-of-canvas legend is removed; the
  inspector's overview breakdown (with counts) is its richer replacement. The
  sr-only node/edge tables stay in the canvas section as the a11y alternative.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — canvas selection + edge clicks + highlight

- **Locations:** `web/frontend/components/feature/GraphCanvas.tsx`.
- **What:** carry the full `GraphNode`/`GraphEdge` on the RF node/link objects.
  New props: `onNodeSelect(node)`, `onEdgeSelect(edge)`, `onBackgroundClick()`,
  `selectedNodeId`, `selectedEdgeKey`. Wire `onNodeClick`→`onNodeSelect(n.node)`
  (all node types now), `onLinkClick`→`onEdgeSelect(l.edge)`,
  `onBackgroundClick`→clear. Draw a **selection ring** on the selected node
  (independent of hover) and render the selected edge **thicker** (`linkWidth`
  accessor keyed on `source|target|type`).
- **Rationale:** the canvas is the source of click events; it must report the full
  element and reflect the current selection visually.
- **Action:** `npm run typecheck` + `npm run lint` on the file. (Canvas is
  jsdom-untestable; behavior verified live in Phase 4.) Commit:
  `Graph Inspector (1/4) Complete: canvas reports node/edge selection + highlights it.`

### Phase 2 — type-count helper + GraphInspectorPanel

- **Locations:** `web/frontend/lib/graphColors.ts` (+ `graphColors.test.ts`),
  new `web/frontend/components/feature/GraphInspectorPanel.tsx`
  (+ `GraphInspectorPanel.test.tsx`).
- **What:** add `graphTypeCounts(nodes, edges)` → `{ nodes: {type,color,count}[], edges: {…}[] }`
  (deduped, sorted, untyped folded). `GraphInspectorPanel` (an `<aside>` mirroring
  `DirectorRail`'s shell) renders: **overview** (node-type + edge-type breakdown
  rows with swatch + type + count, and a "select a node or edge" hint) when nothing
  is selected; **node detail** (name, colored type badge, id, a `<dl>` of metadata)
  or **edge detail** (from→to resolved names, type badge, metadata `<dl>`) with a
  "‹ Back" button (→ `onClear`) when something is selected. Exports the
  `GraphSelection` type.
- **Rationale:** a pure, prop-driven panel is fully unit-testable and owns no fetch.
- **Action:** `npm test -- graphColors GraphInspectorPanel` + typecheck + a11y
  pass (headings, `<dl>`, keyboard-operable back button, counts are text not
  color-only). Commit:
  `Graph Inspector (2/4) Complete: type-count helper + prop-driven GraphInspectorPanel (overview + node/edge detail).`

### Phase 3 — wire selection into GraphView + StoryPlayerView layout

- **Locations:** `web/frontend/components/feature/GraphView.tsx` (+ `GraphView.test.tsx`),
  `web/frontend/features/story-player/StoryPlayerView.tsx` (+ `StoryPlayerView.test.tsx`).
- **What:** `GraphView` gains `selection` state, passes select/clear handlers +
  `selectedNodeId`/`selectedEdgeKey` to `GraphCanvas`, drops the bottom legend and
  the `onNodeSelect` prop, and (populated state only) returns a fragment of the
  canvas `<section>` + `<GraphInspectorPanel>`. `StoryPlayerView`: in Graph mode
  render only `<GraphView>` (which now supplies its own rail); move
  `DirectorRail`/`CharacterDossier` + `TurnInspectorPanel` into the chat branch.
- **Rationale:** co-locating fetch + selection in `GraphView` keeps both panes in
  sync with no parent state; the chat rails are irrelevant while inspecting the graph.
- **Action:** `npm test -- GraphView StoryPlayerView` + typecheck + lint. Commit:
  `Graph Inspector (3/4) Complete: GraphView owns selection + renders the inspector rail; wired into the story player.`

### Phase 4 — full gate + docs + live verify + merge

- **Locations:** `docs/component-map.md`, `docs/design-system.md`, `docs/checklist.md`,
  this plan.
- **What:** full gate — `npm test`, typecheck, lint, `npm run build`, `uv run pytest`.
  **Live-verify** against the running backend (Embergate scenario): overview shows
  the real type breakdown; clicking a node shows its metadata; clicking an edge
  shows its metadata; selection highlights on canvas; background clears. Update docs.
  Merge `graph-inspector-panel` → `main`.
- **Action:** After green + docs, commit:
  `Graph Inspector (4/4) Complete: gate green + docs + live-verified + merge.`

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Canvas selection | node/edge click + background clear + selection highlight | `web/frontend/components/feature/GraphCanvas.tsx` |
| Type-count helper | `graphTypeCounts(nodes, edges)` | `web/frontend/lib/graphColors.ts` |
| Inspector panel | overview breakdown + node/edge property detail | `web/frontend/components/feature/GraphInspectorPanel.tsx` |
| GraphView wiring | selection state + fragment (canvas + inspector) | `web/frontend/components/feature/GraphView.tsx` |
| Player layout | Graph-mode rail = inspector; chat rails hidden | `web/frontend/features/story-player/StoryPlayerView.tsx` |
| Tests | helper + panel + view + player | `web/frontend/**/*.test.{ts,tsx}` |
