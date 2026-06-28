# Storyline Dropdown Counts

## 1. Introduction

The `StorylineMenu` header dropdown already renders a "N scenarios · N cast · N settings" metadata line for each storyline row. However, the counts are computed from the in-memory `Storyline` object's child arrays (`s.scenarios.length`, `s.characters.length`, `s.settings.length`). Child arrays are loaded lazily — `GET /storylines` returns `StorylineSummary` objects (no children), and `useLibraryState.emptyStoryline()` wraps each summary with empty arrays. Children are hydrated only for the **active** storyline. The result: every non-active storyline shows `0 scenarios · 0 cast · 0 settings` in the dropdown at all times.

The fix has two layers. **Backend:** add `scenario_count`, `character_count`, and `setting_count` computed fields to `StorylineRead` via SQL COUNT subqueries in `list_storylines` and the single-get route, so every `GET /storylines` response includes accurate totals without loading child rows. **Frontend:** propagate those count fields through the TypeScript types, the API client, and `useLibraryState`, then update `StorylineMenu` to read the count fields as the primary source (falling back to array length when the arrays are loaded) so the numbers are correct at all times — including for non-active storylines the moment the page loads.

---

## 2. Gaps & Unanswered Questions

- **What happens to single-get counts when `get_storyline` is called internally?** `get_storyline()` in CRUD is used by many callers (update, delete, validation). It will keep returning the ORM model. Only the list route and the single-get *route* need counts — handled by a thin helper function without touching internal callers.
- **Should `setting_count` also be called `worldCount`?** No; the domain object is `Setting`, so `settingCount` is the correct name (matches existing UI copy "settings").
- **Alembic migration needed?** No — this is a query-level change only; no schema column is added.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend: Add counts to `StorylineRead`

#### Step 1.1 — Extend the `StorylineRead` Pydantic schema

- **Location:** `web/backend/app/schemas/storyline.py`
- **Change:** Add three fields to `StorylineRead`:
  ```
  scenario_count: int = 0
  character_count: int = 0
  setting_count: int = 0
  ```
- **Rationale:** These fields default to `0` so the schema is backwards-compatible with any place that constructs a `StorylineRead` without counts (e.g. create/update responses that don't need counts).

#### Step 1.2 — Update `list_storylines` in CRUD to include counts

- **Location:** `web/backend/app/services/crud.py`, function `list_storylines`
- **Change:** Replace the simple `db.scalars(select(Storyline)...)` query with a query that uses correlated scalar subqueries:
  - `SELECT count(*) FROM characters WHERE storyline_id = storylines.id` as `character_count`
  - `SELECT count(*) FROM settings WHERE storyline_id = storylines.id` as `setting_count`
  - `SELECT count(*) FROM scenarios WHERE storyline_id = storylines.id` as `scenario_count`
  - Execute with `db.execute(select(Storyline, char_subq, setting_subq, scenario_subq).order_by(...)).all()`
  - Build and return `list[StorylineRead]` from the resulting rows, populating the count fields.
- **Rationale:** A single SQL round-trip computes all three counts per storyline efficiently. Returning `StorylineRead` Pydantic objects directly means FastAPI no longer serializes raw ORM objects through the response_model — both approaches are valid.
- **Note:** The internal `get_storyline(db, id)` helper is called by update/delete/validate callers and must keep returning the ORM `Storyline` model unchanged.

#### Step 1.3 — Update the `GET /storylines/{id}` route to include counts

- **Location:** `web/backend/app/routes/storylines.py`
- **Change:** Add a helper (or inline query) in the `get_storyline_route` route function that:
  1. Calls `crud.get_storyline(db, storyline_id)` to validate existence and get the ORM object.
  2. Runs three scalar count queries (or a single combined query) to get the child counts.
  3. Constructs and returns a `StorylineRead` with the count fields populated.
- **Rationale:** The single-get route should return the same shape as the list route so the frontend can use counts consistently from both endpoints (create + edit pages call this route).

#### Step 1.4 — Update `create_storyline` and `update_storyline` routes

- **Location:** `web/backend/app/routes/storylines.py`
- **Change:** After `crud.create_storyline` / `crud.update_storyline` returns, annotate the result with `scenario_count=0`/`character_count=0`/`setting_count=0` (create always starts at 0) or query live counts (update). For create, 0 is always correct. For update, the counts don't change so 0 is acceptable — the list re-fetches on switch. Either approach is acceptable; use 0 for simplicity.
- **Rationale:** These routes already return `StorylineRead`; they just need to include the new required fields.

**Action:** Run `uv run pytest utils/tests/backend/` (all tests must pass — particularly `test_storylines.py` if it exists). Run `uv run ruff check web/backend` and `uv run mypy web/backend` (recommended hygiene). Once green, commit locally:
> `[Storyline Dropdown Counts] (1/3) Complete: Backend — add scenario/character/setting counts to StorylineRead via SQL subqueries.`

---

### Phase 2 — Frontend: Types, API client, state hook

#### Step 2.1 — Add count fields to `Storyline` in `types.ts`

- **Location:** `web/frontend/lib/types.ts`, `Storyline` interface
- **Change:** Add three optional fields:
  ```ts
  scenarioCount?: number;
  characterCount?: number;
  settingCount?: number;
  ```
- **Rationale:** The `Storyline` type is the union of the API summary + the hydrated children. Count fields are optional so existing code (seed data, tests) that doesn't set them doesn't break.

#### Step 2.2 — Extend `StorylineSummary` in `api.ts`

- **Location:** `web/frontend/lib/api.ts`, `StorylineSummary` type
- **Change:** `StorylineSummary = Omit<Storyline, "characters" | "settings" | "scenarios">` already inherits any fields added to `Storyline`. Verify that `scenarioCount`, `characterCount`, `settingCount` appear on `StorylineSummary` after Step 2.1 — no further change needed unless the Omit excludes them.
- **Rationale:** The API client already types the list/get endpoints as returning `StorylineSummary`. Once the backend sends counts, they arrive on the deserialized object automatically.

#### Step 2.3 — Propagate counts through `emptyStoryline()` in `useLibraryState`

- **Location:** `web/frontend/features/library/useLibraryState.ts`, `emptyStoryline` helper (line ~36)
- **Current code:** `return { ...summary, characters: [], settings: [], scenarios: [] };`
- **Change:** No code change needed — the spread already carries every field of `summary` (including the new count fields) into the returned `Storyline`. Verify by inspection.
- **Rationale:** When counts arrive from the API in the summary, `emptyStoryline()` naturally propagates them.

**Action:** Run `npm run typecheck` in `web/frontend/` (no TypeScript errors). Run `npm test` to verify existing component tests still pass. Once green, commit locally:
> `[Storyline Dropdown Counts] (2/3) Complete: Frontend types and API client carry scenario/character/setting counts from the backend.`

---

### Phase 3 — `StorylineMenu` UI update + tests

#### Step 3.1 — Update the count display in `StorylineMenu`

- **Location:** `web/frontend/components/feature/StorylineMenu.tsx` (lines ~178–182)
- **Current code:**
  ```tsx
  {s.scenarios.length} scenario{…} · {s.characters.length} cast · {s.settings.length} setting{…}
  ```
- **Change:** Use the count fields as primary, falling back to array length:
  ```tsx
  const scenarioCount = s.scenarioCount ?? s.scenarios.length;
  const characterCount = s.characterCount ?? s.characters.length;
  const settingCount = s.settingCount ?? s.settings.length;
  ```
  Then render `scenarioCount`, `characterCount`, `settingCount` in the metadata line.
- **Rationale:** For non-active storylines the arrays are empty but `scenarioCount` etc. are populated from the API. For the active storyline (fully hydrated), both paths give the correct answer. The fallback keeps tests that construct `Storyline` objects with no count fields (seed data, unit tests) working.

#### Step 3.2 — Update `StorylineMenu.test.tsx`

- **Location:** `web/frontend/components/feature/StorylineMenu.test.tsx`
- **Change:**
  1. Add a test that verifies the count metadata line renders correctly when count fields are set (`scenarioCount: 3`, `characterCount: 5`, `settingCount: 2`) — even with empty child arrays.
  2. Add a test that falls back to array length when count fields are absent (covers seed-data use).
  3. Add the count fields to the `STORYLINES` fixture so existing tests don't show `0 0 0` accidentally (optional — only if a test asserts the count line).
- **Rationale:** The count-display behavior is a new invariant and should be explicitly tested.

#### Step 3.3 — Accessibility + responsive pass

- Per `docs/skills/ada-compliance/SKILL.md` and `docs/skills/accessibility-mobile/SKILL.md`:
  - The count metadata is presentational text — verify it is inside the `<button>` accessible name hierarchy.
  - The metadata spans use `font-mono text-[8.5px]` — confirm contrast ratio against `text-mute` meets WCAG AA (3:1 for small text).
  - Test at 320 / 375 / 768 / 1024 viewports — the dropdown width is fixed at `w-[268px]`; verify no overflow or clipping at 320px.
  - Keyboard: open with Enter/Space, navigate rows with Tab, close with Escape — no regression.

**Action:** Run `npm test` (all component tests green, including new `StorylineMenu` tests). Run `npm run typecheck` + `npm run lint`. Do the accessibility + responsive check above. Once green, commit locally:
> `[Storyline Dropdown Counts] (3/3) Complete: StorylineMenu shows live scenario/cast/setting counts for every storyline at all times.`

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Updated `StorylineRead` schema | Adds `scenario_count`, `character_count`, `setting_count` (default 0) | `web/backend/app/schemas/storyline.py` |
| Updated `list_storylines` CRUD | Computes counts via SQL subqueries; returns `list[StorylineRead]` | `web/backend/app/services/crud.py` |
| Updated `GET /storylines/{id}` route | Returns count fields alongside the storyline summary | `web/backend/app/routes/storylines.py` |
| Updated `Storyline` type | Adds optional `scenarioCount`, `characterCount`, `settingCount` | `web/frontend/lib/types.ts` |
| Updated `StorylineMenu` component | Uses count fields as primary source; array-length fallback | `web/frontend/components/feature/StorylineMenu.tsx` |
| Updated `StorylineMenu` tests | Tests count display with API-backed fields and array-length fallback | `web/frontend/components/feature/StorylineMenu.test.tsx` |
| Updated API contract docs | Documents the new count fields on `StorylineRead` | `docs/api-contract.md` |
