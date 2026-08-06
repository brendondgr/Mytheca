# Plan — UUID-based Storyline/Scenario Routing + Short IDs

## 1. Introduction

Today the Next.js frontend serves the whole Library off `/` (with the active
storyline held only in client state, never in the URL) and plays a scenario at
`/play/[scenarioId]`. There is no shareable, storyline-scoped URL, and the
backend mints long prefixed ids (`sl_1a2b3c4d5e`) via `app/core/ids.py`.

This plan introduces **clean, short, UUID-style routing**:

- **`/{storylineId}`** — the Library scoped to one storyline (the "main URL").
- **`/{storylineId}/{scenarioId}`** — entering a scenario (the story player).

and shortens the two URL-facing id types so the URLs stay tidy: **storyline ids
become pure 8-hex** (`1a2b3c4d`) and **scenario ids become pure 4-hex**
(`9f8e`), both with **no prefix**. All other entity ids (character, setting,
stat, event, session, graph-type) keep their existing prefixed form — they never
appear in a URL. Existing seed slugs (`embergate`, `maerin`) and any
already-stored prefixed ids keep working unchanged because primary keys are
strings.

The approach: (Phase 1) change id generation in the backend with collision-safe
generation for the short, smaller-keyspace ids; (Phase 2) add the two new
App-Router routes, sync the active storyline into the URL, and repoint the
"Enter Scene" link; (Phase 3) validate end-to-end, sweep docs, and merge to
`main`.

---

## 2. Gaps & Unanswered Questions

Resolved with the user:

- **Id format** — storyline = **pure 8-hex, no prefix**; scenario = **pure
  4-hex, no prefix**. Other entities unchanged. *(user-decided)*
- **URL shape** — root-level **`/{storylineId}/{scenarioId}`**; the literal
  `/storyline/` segment from the first ask was dropped in favor of the shorter
  form. *(user-decided)*

Assumptions (simple gaps — proceeding):

- **`/` (root) stays a valid entry point.** It renders the Library as today and,
  once data loads, cosmetically rewrites the URL to `/{activeStorylineId}` via
  `history.replaceState` (no remount, no extra fetch). Deep-linking
  `/{storylineId}` selects that storyline on load.
- **In-session storyline switches** update the URL with `history.replaceState`
  (cosmetic) rather than a Next navigation, to keep the single mounted
  `LibraryView` and its already-hydrated state.
- **4-hex scenario keyspace (65 536)** is ample for a single-user authoring tool,
  but generation will be **collision-checked** against the DB to be safe.
- **`/play/[scenarioId]` is kept as a redirect** (resolves the owning storyline
  from seed/back-end and 308-redirects to the new URL) so old links/bookmarks
  don't break. The story player itself still runs on client seed data (backend
  wiring remains a separate, already-deferred task).
- The player route uses `scenarioId` to resolve the scene (as today);
  `storylineId` is used for the back-link and metadata only.

No complex gaps requiring further human input.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend: short, collision-safe ids for storyline & scenario

- **Locations:**
  - `web/backend/app/core/ids.py` — add `new_hex_id(length: int) -> str`
    (pure `uuid4().hex[:length]`, no prefix). Keep `new_id(prefix)` for all
    other entities.
  - `web/backend/app/models/storyline.py` — default `lambda: new_hex_id(8)`.
  - `web/backend/app/models/scenario.py` — default `lambda: new_hex_id(4)`.
  - `web/backend/app/services/crud.py` — in `create_storyline` and
    `create_scenario`, replace the inline `new_id("sl")` / `new_id("sc")` with a
    small **collision-checked** generator helper (generate → check PK exists →
    retry, bounded attempts) used only when the client supplies no id. The
    `data.id or …` client-supplied path is unchanged.
- **Rationale:** The two id types that surface in URLs must be short and
  prefix-free. The model default covers ORM-side creation; the CRUD path is where
  real creates happen and is where the (small-keyspace scenario) collision check
  belongs. Other entities are intentionally left alone.
- **Tests:** `utils/tests/backend/data/` (or the existing ids/crud test module) —
  assert a generated storyline id is 8 lowercase-hex chars with no `_`, a
  scenario id is 4 hex, both unique across many generations; assert
  client-supplied ids still pass through; assert `new_id(prefix)` is unchanged
  for a character/setting.
- **Docs:** `docs/api-contract.md` (note the id formats for Storyline/Scenario),
  `docs/structure.md` only if the `ids.py` description needs a line.
- **Action:** Run `uv run pytest` for the affected backend areas (data + api).
  Once green (ruff + mypy clean), commit:
  `UUID Routing (1/3) Complete: short prefix-free ids — storyline 8-hex, scenario 4-hex, collision-checked.`

### Phase 2 — Frontend: storyline/scenario routes + URL sync

- **Locations:**
  - `web/frontend/app/[storylineId]/page.tsx` — **new**. Reads `storylineId`
    from `params`, renders `<LibraryView initialStorylineId={storylineId} />`.
    `generateMetadata` titles it generically (`Library · Mytheca`).
  - `web/frontend/app/[storylineId]/[scenarioId]/page.tsx` — **new**. Reads both
    params; resolves the scene from seed by `scenarioId` (mirrors the current
    play page), renders `<StoryPlayerView scenario={…} backHref={'/' + storylineId} />`.
  - `web/frontend/app/play/[scenarioId]/page.tsx` — **convert to redirect**:
    resolve the owning storyline (seed lookup; fall back to first storyline /
    `/`) and `redirect('/' + storylineId + '/' + scenarioId)`.
  - `web/frontend/features/library/LibraryView.tsx` — accept an optional
    `initialStorylineId?: string` prop and thread it into `useLibraryState`.
  - `web/frontend/app/page.tsx` — unchanged render (`<LibraryView />`, no initial
    id); root entry remains valid.
  - `web/frontend/features/library/useLibraryState.ts` —
    - accept `initialStorylineId?` arg; in `loadInitial`, prefer it (when present
      and found in summaries) over `summaries[0]` for the active id + first
      hydrate.
    - add a private `syncUrl(id)` that calls `window.history.replaceState` to
      `/{id}` (guarded for non-browser); call it after `loadInitial` resolves the
      active id, in `switchStoryline`, and after create/delete change the active
      storyline.
  - `web/frontend/components/feature/BeginSceneModal.tsx` — accept `storylineId`
    and change the link from `/play/${s.id}` to `/${storylineId}/${s.id}`.
  - `web/frontend/features/library/LibraryView.tsx` — pass
    `lib.activeStorylineId` into `<BeginSceneModal storylineId={…} />`.
  - `web/frontend/features/story-player/StoryPlayerView.tsx` — accept an optional
    `backHref` and point the existing "back to library" affordance at it
    (default `/`). (If no back affordance exists, add a minimal accessible
    "← Library" link.)
- **Rationale:** Two thin route files give the new URLs without restructuring the
  Library; `initialStorylineId` makes deep links select the right world;
  cosmetic `replaceState` keeps the in-session experience a single mounted view
  while still producing shareable URLs. The redirect preserves old links.
- **Tests:** `web/frontend/...` (co-located Vitest) —
  - update `features/library/LibraryView.editors.test.tsx` expectation
    `/play/embergate` → `/{seedStorylineId}/embergate`.
  - a `useLibraryState` renderHook test: passing `initialStorylineId` makes that
    storyline active after load (mock `api`); `switchStoryline` calls
    `history.replaceState` with `/{id}` (spy).
  - a route smoke test for `app/[storylineId]/page.tsx` (renders LibraryView)
    and the play redirect, consistent with existing route-test patterns
    (mock `next/navigation` as the repo already does where needed).
- **A11y/responsive:** new surfaces are thin wrappers around already-audited
  views; verify the player back-link is keyboard-reachable with visible focus and
  that no layout shifts at 320/375/768/1024. Per the standing shared-dev-server
  constraint (port 3346 under the user's `python app.py`), if an in-browser pass
  isn't possible, verify structurally + via the green suite and record the
  deferral in `docs/checklist.md`.
- **Docs:** `docs/routes.md` (replace `/play/[scenarioId]` row with
  `/{storylineId}` and `/{storylineId}/{scenarioId}`; note `/` redirect-up and
  the legacy `/play` redirect), `docs/component-map.md` (new route files →
  owners), `docs/data-flow.md` if the URL↔state sync warrants a line.
- **Action:** Run `npm test` (Vitest) + `npm run typecheck` + `npm run lint` +
  `npm run build` in `web/frontend`. Once green, commit:
  `UUID Routing (2/3) Complete: /{storylineId} + /{storylineId}/{scenarioId} routes, URL sync, legacy /play redirect.`

### Phase 3 — Validation sweep, docs/status, merge to `main`

- **Locations:** `docs/documentation.md` (status line — note storyline-scoped
  URLs + short ids), `docs/checklist.md` (entry for this work + any deferred
  a11y pass), and a final cross-check of Phase 1/2 doc edits.
- **Rationale:** Single source of truth stays current; status reflects the new
  routing.
- **Validation:** full `uv run pytest` (backend) + full `web/frontend` suite
  (`npm test`, `typecheck`, `lint`, `build`). Confirm: deep-link
  `/{storylineId}` loads that world; `/` rewrites to `/{activeId}`; "Enter Scene"
  → `/{storylineId}/{scenarioId}`; legacy `/play/{scenarioId}` redirects.
- **Merge:** fast-forward/merge the feature branch into `main`, resolving any
  incompatibilities, per the user's instruction. No push.
- **Action:** Once all suites are green and docs updated, commit:
  `UUID Routing (3/3) Complete: validation sweep + docs; merged to main.`

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Short id generator | `new_hex_id(length)` (prefix-free) + collision-checked create | `web/backend/app/core/ids.py`, `web/backend/app/services/crud.py` |
| Storyline/Scenario id defaults | 8-hex / 4-hex model defaults | `web/backend/app/models/storyline.py`, `…/scenario.py` |
| Storyline route | `/{storylineId}` → Library scoped to that world | `web/frontend/app/[storylineId]/page.tsx` |
| Player route | `/{storylineId}/{scenarioId}` → story player | `web/frontend/app/[storylineId]/[scenarioId]/page.tsx` |
| Legacy redirect | `/play/[scenarioId]` → new URL | `web/frontend/app/play/[scenarioId]/page.tsx` |
| URL↔state sync | `initialStorylineId` + `history.replaceState` sync | `web/frontend/features/library/useLibraryState.ts`, `LibraryView.tsx` |
| Enter-scene link | Points at `/{storylineId}/{scenarioId}` | `web/frontend/components/feature/BeginSceneModal.tsx` |
| Backend tests | Id format/uniqueness/passthrough | `utils/tests/backend/data/…` |
| Frontend tests | Route render, redirect, URL sync, updated link | `web/frontend/**/*.test.tsx` |
| Docs | Routes/contract/component-map/status updates | `docs/routes.md`, `docs/api-contract.md`, `docs/component-map.md`, `docs/documentation.md`, `docs/checklist.md` |
</content>
</invoke>
