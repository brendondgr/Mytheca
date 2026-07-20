# Plan — New Storyline context UX: upload-as-category, bigger budget, contained scroll

## 1. Introduction

Three improvements to Mytheca's **New Storyline** page (`StorylineCreatorView` +
`TriagePanel`, backed by `useStorylineCreator` / `storylineCreator`), plus a small
backend budget bump. Today every dropped file lands **Uncategorized** and the author
re-categorizes each row by hand or runs **Triage** to classify them all. We want to
let the author **pick a target bucket first** (Uncategorized / Character / Setting /
Other) — plus the **Draft / RAG** defaults — and then drop a whole batch that all gets
that category in one shot, so a folder of character sheets becomes Characters
instantly with no triage. **Triage stays** as the fallback for whatever is left
Uncategorized (it now classifies *only* the Uncategorized docs, leaving manual choices
alone). Separately, the **context budget** grows from 8K → **32K** chars
(front + back), and the page becomes **self-contained on one screen** with independent
scroll for the Main Body and the Context Files pane (today that only holds at `lg+`;
below it the whole page scrolls).

All of this is frontend except the budget constants (a few backend caps). Scope is the
New Storyline page only — the character/setting modals' `ContextFilesPanel` is
untouched.

## 2. Gaps & Unanswered Questions

- **"32K" = characters** (the existing "8K" is the 8000-char server cap + the meter's
  "~8000 chars" note). So `DOCS_CAP`/`_TOTAL_CAP`/`DOCS_CHAR_CAP` → 32000 and the
  meter's `DRAFT_DOCS_CAP_TOKENS` → 8000 (32000 / 4). Assumption, proceeding.
- **Triage scope after manual categorization:** Triage classifies only docs still
  `category === "select"` (Uncategorized), preserving anything the author/upload
  already bucketed ("if Uncategorized, Triage will Triage the Uncategorized for us").
  Assumption, proceeding.
- **Re-dropping a file with a chosen target:** applies the chosen category + Draft/RAG
  to it (the author explicitly picked a bucket for this batch). Assumption.
- **Contained scroll breakpoint:** real two-column at **`md+`** (≥768; covers the
  laptop widths where the user sees the giant scroll), and a contained *stacked* layout
  below `md` (form pane scrolls; a bounded Context-files pane scrolls) so it is still
  "one screen, two scroll areas" on phones. Assumption, proceeding.
- **Upload default Draft/RAG:** unchanged defaults (Draft off, RAG on) unless the
  author toggles the upload-target controls. Assumption.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Context budget 8K → 32K (backend + frontend constants)
- **Locations:**
  - `web/backend/app/agents/_common.py` `DOCS_CAP` 8000 → 32000.
  - `web/backend/app/agents/triage_agent.py` `_TOTAL_CAP` 8000 → 32000 (+ comment).
  - `web/frontend/lib/readDocs.ts` `DOCS_CHAR_CAP` 8000 → 32000 (+ docstring).
  - `web/frontend/lib/contextBudget.ts` `DRAFT_DOCS_CAP_TOKENS` 2000 → 8000 (+ the
    "~8000 chars server-side" comment → 32000).
- **Rationale:** lets authors ground generation / persist a much larger corpus; both
  sides must agree (the meter advertises the server cap).
- **Tests:** existing `readDocs.test.ts` / `contextBudget.test.ts` reference the
  constants symbolically (no literal `8000`), so they keep passing; confirm. Backend
  build/triage tests don't assert the literal cap; confirm.
- **Action:** `uv run pytest utils/tests/backend/agents` + `npm test -- contextBudget readDocs` (or full vitest). Once green, commit: `Context UX (1/5) Complete: raise the context budget 8K → 32K (front + back).`

### Phase 2 — Upload-as-category data layer (hook + helpers + triage scope)
- **Locations:**
  - `web/frontend/features/library/storylineCreator.ts`: `toCreatorDoc(doc, opts?: {
    category?: DocCategory; useDraft?: boolean; useRag?: boolean })` applies the opts
    (defaults unchanged when omitted).
  - `web/frontend/features/library/useStorylineCreator.ts`: `addFiles(files, opts?)`
    threads the target category + Draft/RAG to new docs (and re-applies to a
    re-dropped name); `triage()` filters to `d.category === "select" && d.text` so it
    only classifies the Uncategorized leftovers.
- **Rationale:** the bulk-categorize behavior is pure state; keeping it in the
  hook/helpers (not the panel) keeps it unit-testable and the panel thin.
- **Tests:** extend `storylineCreator.test.ts` (`toCreatorDoc` with opts) and
  `useStorylineCreator.test.ts` (addFiles-with-category sets the bucket; triage skips
  already-categorized docs).
- **Action:** `npm test -- storylineCreator useStorylineCreator`. Commit: `Context UX (2/5) Complete: bulk upload-as-category + Draft/RAG on upload; Triage only the Uncategorized.`

### Phase 3 — TriagePanel upload-target UI
- **Locations:** `web/frontend/components/feature/TriagePanel.tsx` — add an "Add files
  as" row in the sticky top: a category `<select>` (Uncategorized / Character /
  Setting / Other) + Draft / RAG default toggle chips, held in local panel state and
  passed to `onAddFiles(files, { category, useDraft, useRag })` from both the drop zone
  and the Browse input. Widen the `onAddFiles` prop signature; update the Triage button
  disable/label to key off **uncategorized** docs. `StorylineCreatorView.tsx` passes
  `c.addFiles` (now opts-aware) unchanged.
- **Rationale:** this is the visible feature — choose a bucket, drop a batch, done.
- **Tests:** extend `TriagePanel.test.tsx` (choosing a category + dropping files tags
  them; Triage button reflects uncategorized count) and keep
  `StorylineCreatorView.test.tsx` green.
- **a11y:** the new `<select>` gets a visible/`sr-only` label; toggles use
  `aria-pressed`; controls are keyboard reachable.
- **Action:** `npm test -- TriagePanel StorylineCreatorView` + structural a11y pass.
  Commit: `Context UX (3/5) Complete: TriagePanel upload-target category + Draft/RAG controls.`

### Phase 4 — Self-contained single-screen scroll
- **Locations:** `web/frontend/features/library/StorylineCreatorView.tsx` (the `<main>`
  shell + left wrapper) and the right-pane roots `components/feature/TriagePanel.tsx` +
  `components/feature/WorldBuildPanel.tsx`. Make the shell contained at **all** widths:
  `<main>` `flex h-dvh min-h-0 flex-col overflow-hidden md:flex-row`; left wrapper
  `flex-1 min-h-0 overflow-y-auto`; right panes `flex min-h-0 flex-col … max-h-[42dvh]
  md:max-h-none md:w-[340px] md:shrink-0 md:self-stretch` with the inner body
  `flex-1 min-h-0 overflow-y-auto`. Verify the height chain against `AppShell`
  (`min-h-dvh`; this route has no global header, so `<main h-dvh>` fills the viewport
  exactly → no page scroll).
- **Rationale:** today the contained behavior is gated at `lg`; below it the page
  scrolls as one long body (the reported problem).
- **Tests:** existing render tests stay green; verify `next build` + `tsc`.
- **a11y/responsive:** structural pass at 320 / 375 / 768 / 1024 (no page/horizontal
  overflow; both panes scroll independently; sticky footer reachable) — live in-browser
  pass deferred per the standing shared-dev-server constraint.
- **Action:** `npm test` + `npm run typecheck` + `npm run build`. Commit: `Context UX (4/5) Complete: self-contained single-screen layout with independent Main/Context scroll.`

### Phase 5 — Docs, full validation, merge to main
- **Locations:** `docs/data-flow.md` (upload-as-category + Triage-Uncategorized +
  32K budget), `docs/api-contract.md` (budget cap note), `docs/component-map.md`
  (TriagePanel upload controls if listed), `docs/documentation.md` (status),
  `docs/checklist.md` (this entry).
- **Tests:** full `uv run pytest` + ruff + mypy; frontend `npm run typecheck` + `npm run lint` + `npm test` + `npm run build`.
- **Action:** all green, then merge `feat/storyline-context-upload-ux` → `main` locally
  (resolve any concurrent-session conflicts), commit: `Context UX (5/5) Complete: docs + full validation + merge to main.` Do not push.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Budget bump | 8K → 32K chars front + back | `web/backend/app/agents/_common.py`, `triage_agent.py`, `web/frontend/lib/readDocs.ts`, `lib/contextBudget.ts` |
| Upload-as-category | `addFiles`/`toCreatorDoc` opts + triage-only-uncategorized | `web/frontend/features/library/storylineCreator.ts`, `useStorylineCreator.ts` |
| Upload-target UI | Category select + Draft/RAG default chips in the drop zone | `web/frontend/components/feature/TriagePanel.tsx` |
| Contained scroll | One-screen layout, independent Main/Context scroll | `web/frontend/features/library/StorylineCreatorView.tsx`, `TriagePanel.tsx`, `WorldBuildPanel.tsx` |
| Tests | Helpers, hook, panel, budget | `utils/tests/backend/agents/*`, `web/frontend/**/*.test.ts(x)` |
| Docs | data-flow, api-contract, status, checklist | `docs/*.md` |
